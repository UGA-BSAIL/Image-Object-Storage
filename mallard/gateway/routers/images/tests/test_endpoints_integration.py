"""
Integration tests for the `endpoints` module.
"""


import unittest.mock as mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic.dataclasses import dataclass
from pytest_mock import MockFixture

from mallard.gateway.backends import BackendManager
from mallard.gateway.backends.metadata import MetadataStore
from mallard.gateway.backends.objects import ObjectStore
from mallard.gateway.routers.images import filled_uav_metadata, router
from mallard.type_helpers import ArbitraryTypesConfig


@dataclass(frozen=True, config=ArbitraryTypesConfig)
class ConfigForTests:
    """
    Encapsulates standard configuration for most tests.

    Args:
        client: The `TestClient` to use.
        mock_manager_class: The mocked `BackendManager` class.
        mock_filled_metadata: The mocked `_filled_uav_metadata` dependency.
    """

    client: TestClient
    mock_manager_class: BackendManager
    mock_filled_metadata: mock.Mock


@pytest.fixture
def app() -> FastAPI:
    """
    Creates the `FastAPI` app to use for tests.

    Returns:
        The app that it created.

    """
    app = FastAPI(debug=True)
    app.include_router(router)

    return app


@pytest.fixture
def config(mocker: MockFixture, app: FastAPI) -> ConfigForTests:
    """
    Generates standard configuration for most tests.

    Args:
        mocker: The fixture to use for mocking.
        app: The FastAPI application to use for testing.

    Returns:
        The configuration that it created.

    """
    mock_manager_class = mocker.create_autospec(BackendManager)
    mock_manager = mock_manager_class.return_value
    # These don't get auto-specced for some reason, so we have to do them
    # manually.
    mock_manager.object_store = mocker.create_autospec(
        ObjectStore, instance=True
    )
    mock_manager.metadata_store = mocker.create_autospec(
        MetadataStore, instance=True
    )

    mock_filled_metadata = mocker.Mock()

    # Override FastAPI dependencies.
    app.dependency_overrides[BackendManager] = mock_manager_class
    app.dependency_overrides[filled_uav_metadata] = mock_filled_metadata

    # Fake metadata filler will return the input metadata unchanged.
    mock_filled_metadata.side_effect = lambda m, _, __: m

    # Create the test client.
    client = TestClient(app)

    yield ConfigForTests(
        client=client,
        mock_manager_class=mock_manager_class,
        mock_filled_metadata=mock_filled_metadata,
    )

    # Clean up by removing the mocked dependencies.
    app.dependency_overrides = {}


# def test_create_uav_image(config: ConfigForTests, faker: Faker) -> None:
#     """
#     Tests that the `create_uav_image` endpoint works.
#
#     Args:
#         config: The configuration to use for testing.
#         faker: The fixture to use for generating fake data.
#
#     """
#     # Arrange.
#     # Create a default metadata structure.
#     metadata = UavImageMetadata()
#
#     # Create a fake image.
#     image = faker.image()
#     files = {"image_data": (faker.file_name(category="image"), image)}
#
#     # Act.
#     response = config.client.post(
#         "/images/create_uav",
#         data=flatten_model(metadata),
#         files=files,
#         params={"tz": 0},
#     )
#
#     # Assert.
#     # Request should have worked.
#     assert response.status_code == 201
