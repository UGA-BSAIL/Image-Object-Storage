import { css, html, LitElement, property } from "lit-element";
import "@material/mwc-icon";
import "@material/mwc-fab";

/**
 * An element that allows the user to select and upload files.
 */
export class FileUploader extends LitElement {
  /** Tag name for this element. */
  static tagName: string = "file-uploader";
  static styles = css`
    /** Content on the bottom layer is scrollable and occluded by
     content on top. */
    .bottom_layer {
      position: relative;
      z-index: 5;
      background-color: var(--theme-light-gray);
      overflow: auto;
    }

    /** Content on the top layer doesn't scroll. */
    .top_layer {
      position: fixed;
      z-index: 10;
    }

    .drop_zone {
      height: 100px;
      border-radius: 25px;
      padding: 20px 0;
      border-width: 5px;
      border-style: dashed;

      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      align-items: center;
    }

    /** Show shadow only along bottom of the drop zone. */
    #drop_zone_container {
      min-width: 500px;
      overflow: hidden;
      padding-bottom: 10px;
      margin-left: -24px;
      margin-right: -24px;
    }

    /** Place the drop zone on it's own plane above the other content. */
    #drop_zone_card {
      padding: 5px 24px 40px 24px;
      background: white;
    }

    .file_list {
      min-width: 500px;
      min-height: 100px;
      padding-top: 130px;
      margin-left: -24px;
      margin-right: -24px;
    }

    #upload_icon {
      --mdc-icon-size: 75px;
    }

    #upload_help {
      font-family: "Roboto", sans-serif;
      font-weight: 200;
    }

    /* Allows us to force a new row in a flexbox layout. */
    .break {
      flex-basis: 100%;
      height: 0;
    }

    /* Styles UI when no file is being dragged. */
    .no_drag {
      border-color: var(--theme-gray);
      color: var(--theme-gray);
    }

    /** Styles UI when a file is being dragged. */
    .active_drag {
      border-color: var(--theme-primary);
      color: var(--theme-primary);
    }

    #browse {
      position: relative;
      z-index: 15;
      top: 167px;
      right: -90%;
    }
  `;

  /**
   * Keeps track of whether the user is actively dragging something
   * over the drop target.
   */
  @property({ type: Boolean, attribute: false })
  isDragging: boolean = false;

  /**
   * Handles the drop event over the drop zone.
   * @param {Event} event The event to handle.
   * @protected
   */
  protected handleDrop(event: Event) {
    console.log("Got drop event: " + event);
    event.preventDefault();
  }

  /**
   * Handles the user dragging something over the drop zone.
   * @param {Event} event The event to handle.
   * @protected
   */
  protected handleDragEnter(event: Event) {
    event.preventDefault();
    this.isDragging = true;
  }

  /**
   * Handles the user dragging something out of the drop zone.
   * @param {Event} event The event to handle.
   * @protected
   */
  protected handleDragLeave(event: Event) {
    event.preventDefault();
    this.isDragging = false;
  }

  /**
   * @inheritDoc
   */
  protected render() {
    // React to drag events.
    const dropZoneClass: string = this.isDragging ? "active_drag" : "no_drag";

    return html`
      <link rel="stylesheet" href="./static/mallard-edge.css" />
      <div id="drop_zone_container" class="top_layer">
        <div id="drop_zone_card" class="mdc-elevation--z2">
          <div
            id="upload_drop_zone"
            class="drop_zone ${dropZoneClass}"
            @drop="${this.handleDrop}"
            @dragenter="${this.handleDragEnter}"
            @dragleave="${this.handleDragLeave}"
          >
            <mwc-icon id="upload_icon" class="${dropZoneClass}"
              >upload_file</mwc-icon
            >
            <div class="break"></div>
            <p id="upload_help" class="${dropZoneClass}">
              Drag files here to upload.
            </p>
          </div>
        </div>
      </div>
      <mwc-fab icon="add" id="browse"></mwc-fab>
      <div class="file_list bottom_layer"></div>
    `;
  }
}
