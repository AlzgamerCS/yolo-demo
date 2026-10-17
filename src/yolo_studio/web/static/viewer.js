// iPhone browsers may not support element fullscreen; fill the viewport instead.
async function toggleViewerFullscreen(viewer) {
  if (document.fullscreenElement) {
    await document.exitFullscreen();
    return;
  }
  if (viewer.classList.contains("expanded")) {
    viewer.classList.remove("expanded");
    document.body.classList.remove("viewer-expanded");
    return;
  }
  if (viewer.requestFullscreen && document.fullscreenEnabled) {
    try {
      await viewer.requestFullscreen();
      return;
    } catch {
      /* Fall back when the browser refuses native fullscreen. */
    }
  }
  viewer.classList.add("expanded");
  document.body.classList.add("viewer-expanded");
}
