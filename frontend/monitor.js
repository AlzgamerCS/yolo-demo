const $ = (id) => document.getElementById(id);
let frameId = -1,
  lastUrl = null,
  currentClient = "",
  alive = true,
  requestGeneration = 0;
function reset() {
  frameId = -1;
  requestGeneration++;
  $("feed").hidden = true;
  $("empty").hidden = false;
}
$("client").onchange = () => {
  currentClient = $("client").value;
  reset();
};
$("kind").onchange = reset;
$("fullscreen").onclick = async () => {
  if (document.fullscreenElement) await document.exitFullscreen();
  else await $("viewer").requestFullscreen();
};
async function clients() {
  while (alive) {
    try {
      const response = await fetch("/api/operator/sessions");
      if (!response.ok)
        throw new Error(
          "Open this monitor on the backend laptop at http://127.0.0.1:8765/monitor.",
        );
      const data = await response.json();
      $("error").hidden = true;
      const ids = data.sessions.map((client) => client.id);
      if (!ids.includes(currentClient)) {
        currentClient = ids[0] || "";
        reset();
      }
      $("client").replaceChildren(
        ...(data.sessions.length
          ? data.sessions.map((client) => {
              const option = document.createElement("option");
              option.value = client.id;
              option.textContent = `${client.label} · ${client.phase}`;
              return option;
            })
          : [new Option("No sharing clients connected", "")]),
      );
      $("client").value = currentClient;
      const client = data.sessions.find(
        (client) => client.id === currentClient,
      );
      $("status").textContent = client
        ? `${client.label} · ${client.metrics.resolution || "waiting for video"}`
        : "No client selected";
    } catch (error) {
      $("error").textContent = error.message;
      $("error").hidden = false;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}
async function frames() {
  while (alive) {
    if (currentClient) {
      const token = requestGeneration;
      try {
        const response = await fetch(
          `/api/operator/frame/${currentClient}?kind=${$("kind").value}&after=${frameId}`,
        );
        if (response.status === 200) {
          const blob = await response.blob();
          if (token === requestGeneration) {
            const next = URL.createObjectURL(blob),
              previous = lastUrl;
            await new Promise((resolve) => {
              $("feed").onload = resolve;
              $("feed").onerror = resolve;
              $("feed").src = next;
            });
            lastUrl = next;
            if (previous) URL.revokeObjectURL(previous);
            frameId = Number(response.headers.get("X-Frame-Id"));
            $("feed").hidden = false;
            $("empty").hidden = true;
          }
        } else if (response.status === 403 || response.status === 404) {
          reset();
        }
      } catch (error) {
        reset();
      }
    }
    await new Promise((resolve) =>
      setTimeout(resolve, currentClient ? 30 : 300),
    );
  }
}
window.onpagehide = () => {
  alive = false;
  if (lastUrl) URL.revokeObjectURL(lastUrl);
};
clients();
frames();
