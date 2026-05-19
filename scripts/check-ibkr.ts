import net from "net";

const PORTS = [
  { port: 7497, label: "TWS Paper Trading" },
  { port: 7496, label: "TWS Live Trading" },
  { port: 4001, label: "IB Gateway Live" },
  { port: 4002, label: "IB Gateway Paper" },
];

async function checkPort(host: string, port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    socket.setTimeout(1000);
    socket
      .connect(port, host, () => { socket.destroy(); resolve(true); })
      .on("error", () => resolve(false))
      .on("timeout", () => { socket.destroy(); resolve(false); });
  });
}

console.log("Checking IBKR connection ports...\n");

for (const { port, label } of PORTS) {
  const open = await checkPort("127.0.0.1", port);
  console.log(`${open ? "✅" : "❌"}  ${label.padEnd(25)} localhost:${port}`);
}

console.log(`
If all closed:
  IBKR Desktop → Settings → API → enable socket on port 7497
  Make sure 127.0.0.1 is in trusted IPs
`);
