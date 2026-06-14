let ws;

function connectWS(symbol) {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(
    `${protocol}://${window.location.host}/ws/price/${symbol}/`,
  );

  ws.onopen = function () {
    console.log(`Connected to ${symbol}`);
  };

  ws.onmessage = function (e) {
    const data = JSON.parse(e.data);
    console.log("Data is :", data);
  };

  ws.onclose = function () {
    console.log("WebSocket closed — reconnecting in 3s...");
    setTimeout(() => connectWS(symbol), 3000); // reconnect, don't reload
  };

  ws.onerror = function (err) {
    console.error("WebSocket error:", err);
  };
}

connectWS("OTV19");
