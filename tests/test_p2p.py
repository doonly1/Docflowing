#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P2P mDNS Discovery Test
Run this on two machines in the same LAN to test node discovery.
"""
import sys
import os
import time

# 配置路径（与 server/__init__.py 保持一致）
_tests_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(_tests_dir)
sys.path.insert(0, os.path.join(project_root, 'tools'))
sys.path.insert(0, project_root)

from p2p.discovery import NodeDiscovery


def test_basic_flow():
    print("=" * 60)
    print("P2P mDNS Discovery Test")
    print("=" * 60)

    # 1. Create a NodeDiscovery instance
    print("\n[1] Creating NodeDiscovery instance...")
    discovery = NodeDiscovery(
        node_id="test-node-001",
        display_name="Test Node",
        port=5000,
        public_key_b64="dGVzdC1wdWJsaWMta2V5"
    )
    print(f"    Node ID: {discovery.node_id}")
    print(f"    Display: {discovery.display_name}")
    print(f"    Port: {discovery.port}")

    # 2. Start discovery
    print("\n[2] Starting mDNS discovery...")
    discovery.start()
    print("    Discovery started!")
    print("    Service type: _docflow-p2p._tcp.local.")
    print("    Waiting 8 seconds for service registration & browsing...")

    time.sleep(8)

    # 3. Check discovered nodes
    print("\n[3] Checking discovered nodes...")
    nodes = discovery.get_discovered_nodes()
    print(f"    Found {len(nodes)} node(s):")
    if nodes:
        for n in nodes:
            print(f"    - {n['display_name']} ({n['node_id'][:8]}) @ {n['addr']}")
    else:
        print("    (none - run another instance to see cross-discovery)")

    # 4. Run discovery for a bit longer
    print("\n[4] Keeping discovery alive for 10 more seconds...")
    for i in range(10):
        time.sleep(1)
        nodes_now = discovery.get_discovered_nodes()
        sys.stdout.write(f"\r    t={i+1}s  nodes={len(nodes_now)}  ")
        sys.stdout.flush()
    print()

    nodes = discovery.get_discovered_nodes()
    print(f"    Final node count: {len(nodes)}")

    # 5. Stop discovery
    print("\n[5] Stopping mDNS discovery...")
    discovery.stop()
    print("    Discovery stopped.")

    print("\n" + "=" * 60)
    print("TEST PASSED")
    print("=" * 60)
    print("\nTip: Run this on 2+ machines in the same LAN to verify cross-node discovery.")
    print("     The test node registers but won't discover itself (by design).")


def test_cleanup():
    """Verify cleanup doesn't leave resources"""
    print("\n" + "=" * 60)
    print("[Extra] Testing cleanup (start/stop cycle)")
    print("=" * 60)

    d = NodeDiscovery(node_id="cleanup-test", display_name="Cleanup", port=5000)

    for i in range(3):
        print(f"    Cycle {i+1}: start...")
        d.start()
        time.sleep(2)
        print(f"    Cycle {i+1}: stop...")
        d.stop()
        time.sleep(1)

    print("    Multiple start/stop cycles: OK")


if __name__ == "__main__":
    try:
        test_basic_flow()
        test_cleanup()
        sys.exit(0)
    except Exception as e:
        print(f"\nFAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
