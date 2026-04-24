from pox.core import core
import pox.openflow.libopenflow_01 as of
from pox.lib.util import dpid_to_str, str_to_dpid
from pox.lib.util import str_to_bool
import time

# Logger → used to print messages on terminal
log = core.getLogger()

# Delay before flooding starts (0 = no delay)
_flood_delay = 0


class LearningSwitch(object):

  def __init__(self, connection, transparent):
    # connection → connection between controller and switch
    self.connection = connection

    # transparent → whether to filter special packets (LLDP etc.)
    self.transparent = transparent

    # Dictionary to store MAC address → port mapping
    self.macToPort = {}

    # Listen for PacketIn events from switch
    connection.addListeners(self)

    # Check if flood delay is already finished
    self.hold_down_expired = (_flood_delay == 0)


  def _handle_PacketIn(self, event):
    # This function runs EVERY TIME a packet comes to controller

    # Extract actual packet from event
    packet = event.parsed


    # -------- FLOOD FUNCTION --------
    def flood(message=None):
      # Create a packet_out message
      msg = of.ofp_packet_out()

      # Check if flood delay time has passed
      if time.time() - self.connection.connect_time >= _flood_delay:

        # First time flooding → print message
        if not self.hold_down_expired:
          self.hold_down_expired = True
          log.info("%s: Flood started", dpid_to_str(event.dpid))

        # Optional debug message
        if message:
          log.debug(message)

        # Send packet to ALL ports except incoming port
        msg.actions.append(of.ofp_action_output(port=of.OFPP_FLOOD))

      # Attach original packet data
      msg.data = event.ofp

      # Set incoming port
      msg.in_port = event.port

      # Send packet to switch
      self.connection.send(msg)


    # -------- DROP FUNCTION --------
    def drop(duration=None):

      # If duration is given → install drop rule in switch
      if duration:
        if not isinstance(duration, tuple):
          duration = (duration, duration)

        msg = of.ofp_flow_mod()

        # Match same type of packet
        msg.match = of.ofp_match.from_packet(packet)

        # Time after which rule expires
        msg.idle_timeout = duration[0]
        msg.hard_timeout = duration[1]

        # Reference to packet buffer
        msg.buffer_id = event.ofp.buffer_id

        # Send drop rule to switch
        self.connection.send(msg)

      # If no duration → drop only this packet
      elif event.ofp.buffer_id:
        msg = of.ofp_packet_out()
        msg.buffer_id = event.ofp.buffer_id
        msg.in_port = event.port
        self.connection.send(msg)


    # -------- STEP 1: LEARN SOURCE --------
    # Store: source MAC → incoming port
    self.macToPort[packet.src] = event.port


    # -------- STEP 2: FILTER SPECIAL PACKETS --------
    if not self.transparent:
      # Ignore LLDP and special control packets
      if packet.type == packet.LLDP_TYPE or packet.dst.isBridgeFiltered():
        drop()
        return


    # -------- STEP 3: MULTICAST --------
    # If destination is multicast → send everywhere
    if packet.dst.is_multicast:
      flood()


    else:
      # -------- STEP 4: UNKNOWN DESTINATION --------
      # If we don’t know destination MAC → flood
      if packet.dst not in self.macToPort:
        flood("Destination unknown → flooding")

      else:
        # Get output port from table
        port = self.macToPort[packet.dst]


        # -------- STEP 5: SAME PORT --------
        # If packet comes and goes to same port → drop
        if port == event.port:
          log.warning("Packet coming and going to same port → dropped")
          drop(10)
          return


        # -------- STEP 6: INSTALL FLOW RULE --------
        # Tell switch: next time send directly (no controller needed)

        log.debug("Installing flow rule in switch")

        msg = of.ofp_flow_mod()

        # Match this type of packet
        msg.match = of.ofp_match.from_packet(packet, event.port)

        # Rule expiry times
        msg.idle_timeout = 10
        msg.hard_timeout = 30

        # Action → send to correct port
        msg.actions.append(of.ofp_action_output(port=port))

        # Include current packet
        msg.data = event.ofp

        # Send rule to switch
        self.connection.send(msg)



# -------- CONTROLLER CLASS --------
class l2_learning(object):

  def __init__(self, transparent, ignore=None):

    # Listen for new switches connecting
    core.openflow.addListeners(self)

    self.transparent = transparent

    # Ignore certain switches if needed
    self.ignore = set(ignore) if ignore else ()


  def _handle_ConnectionUp(self, event):

    # If switch is ignored → do nothing
    if event.dpid in self.ignore:
      return

    # Create LearningSwitch object for this switch
    LearningSwitch(event.connection, self.transparent)



# -------- MAIN FUNCTION --------
def launch(transparent=False, hold_down=_flood_delay, ignore=None):

  global _flood_delay

  # Set flood delay value
  _flood_delay = int(str(hold_down), 10)

  # Process ignore list
  if ignore:
    ignore = ignore.replace(',', ' ').split()
    ignore = set(str_to_dpid(dpid) for dpid in ignore)

  # Start controller
  core.registerNew(l2_learning, str_to_bool(transparent), ignore)
