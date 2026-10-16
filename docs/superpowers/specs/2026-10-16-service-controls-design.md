# Service controls without wiring board

The hub will remove the visual wiring board and its separate route. Carrier changes, health checks, and V2Ray copy actions will be available beside each service on both Iran and node pages. The routing page remains a read-only topology/console view.

The Iran service record is authoritative for the selected carrier. A node service can be in the rathole or Backhaul lane; its row must show that lane without suggesting that a configured record proves connectivity. Both pages use one carrier-change workflow and refresh server state after each attempt. Failed migration must retain or restore the prior working lane where possible and report the exact failure.

The V2Ray copy action asks for the user's real UUID; the hub does not know it. The UI must not copy a link containing a fake UUID.

Verification covers UI placement, legacy wiring URL behavior, Backhaul-to-Noise migration and failure cleanup, and the copied link's UUID.
