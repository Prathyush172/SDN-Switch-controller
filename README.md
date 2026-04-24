# SDN Learning Switch Controller

This project implements a learning switch using POX controller.

## How to run
1. Start controller:
   ./pox.py forwarding.l2_learning.py

2. Start Mininet:
   sudo mn --topo single,3 --controller remote

3. Test:
   pingall
   h1 ping -c 3 h2

4. View flows:
   sh ovs-ofctl dump-flows s1
