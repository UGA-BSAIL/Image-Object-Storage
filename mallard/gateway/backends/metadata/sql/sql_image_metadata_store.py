"""
A metadata store that interfaces with a SQL database.
"""

from contextlib import asynccontextmanager
from enum import Enum
from functools import cache, singledispatchmethod
from typing import (
    Any,
    AsyncIterable,
    AsyncIterator,
    Dict,
    Iterable,
    Optional,
    Tuple,
)

from confuse import ConfigView
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.future import Select, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.orm.exc import NoResultFound

from ...objects.models import ObjectRef
from .. import ImageMetadataStore
from ..schemas import (
    GeoPoint,
    ImageMetadata,
    ImageQuery,
    Ordering,
    UavImageMetadata,
)
from .models import Image


@cache
def _create_session_maker(db_url: str) -> sessionmaker:
    """
    Creates the `sessionmaker` for a particular database.

    Args:
        db_url: The URL of the database.

    Returns:
        The appropriate session-maker.

    """
    engine = create_async_engine(db_url)
    return sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class SqlImageMetadataStore(ImageMetadataStore):
    """
    A metadata store that interfaces with a SQL database.
    """

    _ORDER_TO_COLUMN: Dict[Ordering.Field, InstrumentedAttribute] = {
        Ordering.Field.NAME: Image.name,
        Ordering.Field.SESSION_NUM: Image.session_number,
        Ordering.Field.SEQUENCE_NUM: Image.sequence_number,
        Ordering.Field.CAPTURE_DATE: Image.capture_date,
        Ordering.Field.CAMERA: Image.camera,
    }
    """
    Maps orderings to corresponding columns in the ORM.
    """

    @classmethod
    @asynccontextmanager
    async def from_config(
        cls: ImageMetadataStore.ClassType, config: ConfigView
    ) -> AsyncIterator[ImageMetadataStore.ClassType]:
        # Extract the configuration.
        db_url = config["endpoint_url"].as_str()

        logger.info("Connecting to SQL database at {}.", db_url)

        # Create the session.
        session_maker = _create_session_maker(db_url)
        async with session_maker() as session:
            yield cls(session)

    def __init__(self, session: AsyncSession):
        """
        Args:
            session: The session to use for communicating with the database.

        """
        self.__session = session

    @staticmethod
    def __orm_image_to_pydantic(image: Image) -> UavImageMetadata:
        """
        Converts an ORM image model to a Pydantic model.

        Args:
            image: The image model to convert.

        Returns:
            The converted model.

        """
        metadata = UavImageMetadata.from_orm(image)

        # Set the location correctly.
        location = GeoPoint(
            latitude_deg=image.location_lat, longitude_deg=image.location_lon
        )
        return metadata.copy(update=dict(location=location))

    @staticmethod
    def __pydantic_to_orm_image(
        object_id: ObjectRef, metadata: ImageMetadata
    ) -> Image:
        """
        Converts a Pydantic metadata model to an ORM image model.

        Args:
            object_id: The corresponding reference to the image in the object
                store.
            metadata: The Pydantic model to convert.

        Returns:
            The converted model.

        """
        # Convert to the format used by the database.
        model_attributes = metadata.dict(exclude={"location"})
        # Convert location format.
        location_lat = metadata.location.latitude_deg
        location_lon = metadata.location.longitude_deg

        return Image(
            bucket=object_id.bucket,
            key=object_id.name,
            location_lat=location_lat,
            location_lon=location_lon,
            **model_attributes,
        )

    async def __get_by_id(self, object_id: ObjectRef) -> Image:
        """
        Gets a particular image from the database by its unique ID.

        Args:
            object_id: The unique ID of the image.

        Returns:
            The ORM image that it retrieved.

        Raises:
            - `KeyError` if no such image exists.

        """
        query = select(Image).where(
            Image.bucket == object_id.bucket, Image.key == object_id.name
        )
        query_results = await self.__session.execute(query)

        try:
            return query_results.scalars().one()
        except NoResultFound:
            raise KeyError(f"No metadata for image '{object_id}'.")

    # TODO (danielp): These should be classmethods, but Python issue 39679
    #  prevents this.
    @singledispatchmethod
    def __update_query(
        self,
        value: Any,
        *,
        query: Select,
        column: InstrumentedAttribute,
    ) -> Select:
        """
        Updates a query to filter for user-specified conditions. For instance,
        a raw int will cause it to generate a query that looks for exact
        equality to that value.

        Args:
            value: The value that we want to filter the query with.
            query: The existing query to add to.
            column: The specific column that we are filtering on.

        Returns:
            The modified query.

        """
        raise NotImplementedError(
            f"__update_query is not implemented for type {type(value)}."
        )

    @__update_query.register
    def _(
        self,
        value: type(None),
        *,
        query: Select,
        column: InstrumentedAttribute,
    ) -> Select:
        # Not specified in the query. Don't add a filter for this.
        return query

    @__update_query.register
    def _(
        self,
        value: Enum,
        *,
        query: Select,
        column: InstrumentedAttribute,
    ) -> Select:
        return query.where(column == value)

    @__update_query.register
    def _(
        self,
        value: str,
        *,
        query: Select,
        column: InstrumentedAttribute,
    ) -> Select:
        return query.where(column.like(f"%{value}%"))

    @__update_query.register
    def _(
        self,
        value: ImageQuery.Range,
        *,
        query: Select,
        column: InstrumentedAttribute,
    ) -> Select:
        return query.where(
            column >= value.min_value, column <= value.max_value
        )

    @staticmethod
    def __update_location_query(
        value: Optional[ImageQuery.BoundingBox],
        *,
        query: Select,
        lat_column: InstrumentedAttribute,
        lon_column: InstrumentedAttribute,
    ) -> Select:
        """
        Updates a query to filter for a specified location.

        Args:
            value: The bounding box around the location.
            query: The query to update.
            lat_column: The column containing the location latitude.
            lon_column: The column containing the location longitude.

        Returns:
            The updated query.

        """
        if value is None:
            # No bounding box was specified, so this doesn't need updating.
            return query

        return query.where(
            lat_column <= value.north_east.latitude_deg,
            lat_column >= value.south_west.latitude_deg,
            lon_column <= value.north_east.longitude_deg,
            lon_column >= value.south_west.longitude_deg,
        )

    def __update_image_query(
        self,
        value: ImageQuery,
        *,
        query: Select,
    ) -> Select:
        # Shortcut for applying a selection of filters to a query.
        def _apply_query_updates(
            updates: Iterable[Tuple[Any, InstrumentedAttribute]]
        ) -> Select:
            _query = query
            for _value, column in updates:
                _query = self.__update_query(
                    _value, column=column, query=_query
                )
            return _query

        # Build the complete query.
        query = _apply_query_updates(
            [
                (value.platform_type, Image.platform_type),
                (value.name, Image.name),
                (value.notes, Image.notes),
                (value.camera, Image.camera),
                (value.session_numbers, Image.session_number),
                (value.sequence_numbers, Image.sequence_number),
                (value.capture_dates, Image.capture_date),
                (value.location_description, Image.location_description),
                (value.altitude_meters, Image.altitude_meters),
                (value.gsd_cm_px, Image.gsd_cm_px),
            ]
        )
        query = self.__update_location_query(
            value.bounding_box,
            query=query,
            lat_column=Image.location_lat,
            lon_column=Image.location_lon,
        )

        return query

    @classmethod
    def __update_query_order(cls, order: Ordering, *, query: Select) -> Select:
        """
        Updates a query with the specified ordering.

        Args:
            order: The ordering to use.
            query: The query to update.

        Returns:
            The updated query.

        """
        column_spec = cls._ORDER_TO_COLUMN[order.field]
        if not order.ascending:
            # It should be in descending order.
            column_spec = column_spec.desc()

        return query.order_by(column_spec)

    async def add(
        self, *, object_id: ObjectRef, metadata: ImageMetadata
    ) -> None:
        logger.debug("Adding metadata for object {}.", object_id)

        # Add the new image.
        image = self.__pydantic_to_orm_image(object_id, metadata)
        async with self.__session.begin():
            self.__session.add(image)

    async def get(self, object_id: ObjectRef) -> UavImageMetadata:
        return self.__orm_image_to_pydantic(await self.__get_by_id(object_id))

    async def delete(self, object_id: ObjectRef) -> None:
        logger.debug("Deleting metadata for object {}.", object_id)

        async with self.__session.begin():
            orm_image = await self.__get_by_id(object_id)
            await self.__session.delete(orm_image)

    async def query(
        self,
        query: ImageQuery,
        orderings: Iterable[Ordering] = (),
        skip_first: int = 0,
        max_num_results: int = 500,
    ) -> AsyncIterable[ObjectRef]:
        # Create the SQL query.
        selection = select(Image)
        selection = self.__update_image_query(query, query=selection)

        # Apply the specified orderings.
        for order in orderings:
            selection = self.__update_query_order(order, query=selection)

        # Apply skipping and limiting.
        selection = selection.offset(skip_first).limit(max_num_results)

        # Execute the query.
        query_results = await self.__session.execute(selection)

        for result in query_results.scalars():
            yield ObjectRef(bucket=result.bucket, name=result.key)
