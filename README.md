# What is this?

This is an extremely early attempt at writing a Python client for controlling a Gree mini-split heat pump over Wifi. These are typically sold in the US under various brands like Bryant, Carrier, etc. Typically they'll come with a wireless remote (claiming to be IR, while actually being RF) but they are advertised as supporting wifi-based control as well. These units can often be identified by having a yellow flashing light behind the front cover, whenever the Wifi function is enabled via the wireless remote.

Unfortunately, these days the options for wifi-based control are limited. The user manual will point you to the G-Life Android App, which crashes immediately on any reasonably-modern Android device. Options for control include allowing the unit to operate in Wireless AP mode (and connecting a client to the AP), or switching the unit into STA (wifi client) mode and allowing it to join your home wifi network (which may have security implications, since the unit will try to ping a server in China). We will be starting with the AP approach. The default wifi password on the AP is 12345678.

# Protocol
The client opens a TCP connection to the heat pump and can periodically request a status update, or publish a configuration update. Most of the heat pump's parameters are updated using a single update packet, though some parameters (power-saving mode?) require an extended config packet (still TBD). Secondary parameters (such as wifi password, AP/STA mode, etc) are set through dedicated config packets, but the main heat pump functions (temperature, schedule, etc) are all updated using a unified config packet.

Most of the protocol details were obtained through a combination of trial and error, wireless sniffing, and decompiling of the (now defunct) G-Life Mobile App.


