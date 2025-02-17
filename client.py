#!/usr/bin/python3.8

from enum import Enum
import socket
import time
import copy
import select

def GetBits(val, lsb_pos, n_bits = 1):
    return (val >> lsb_pos) & ((1 << n_bits) - 1)

def GetBit(val, lsb_pos):
    return (val & (1 << lsb_pos)) != 0

def DumpByte(buf, pos, label = "buf"):
    print(f"{label}[{pos}] = {buf[pos]:02x}")

def ToBit(val, bit):
    return val << bit

def DumpBuffer(label, buf, verbose = False):
    if not buf:
        print(f"{label} = None")
        return
    
    if not verbose:
        print(label + " = " + " ".join([f"{v:02x}" for v in buf]) + "")
        return
    
    for i in range(0, len(buf)):
        print(f"buf[{i}] = {buf[i]:02x}")


class DeviceSocket:
    def __init__(self):
        self.socket = None
    
    def Open(self):
        if self.socket:
            print("Socket already open?")
            return False

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        return self.socket.connect(('192.168.0.1', 6000))

    def Close(self):
        if not self.socket:
            return False

        self.socket.close()

        return True

    def SendRaw(self, buf):
        if not buf:
            return False

        return self.socket.send(buf)
    
    def SendConfig(self, cfg):
        if not cfg:
            return False

        encoded = cfg.Encode()

        if not encoded:
            return False

        return self.SendRaw(bytes(encoded))


    def SendQuery(self):
        buf = bytearray(5)
        buf[0] = 0x7e
        buf[1] = 0x7e
        buf[2] = 0x02
        buf[3] = 0x02
        DeviceSocket.SetChecksum(buf)
        self.SendRaw(buf)


    @staticmethod
    def CalcChecksum(buf):
        length = len(buf)
        cs = 0
        if length < 4:
            print(f"Buffer length too short for a checksum? {length}")
            return None

        for i in range(2, length - 1):
            cs += buf[i]

        return cs & 0xff


    @staticmethod
    def SetChecksum(buf):
        buf[len(buf) - 1] = DeviceSocket.CalcChecksum(buf)


    def Read(self):
        header = self.socket.recv(3)
        
        if header[0] != 0x7e or header[1] != 0x7e or header[2] > 60:
            print(f"Invald header?")
            DumpBuffer("header", header)
            return None

        remaining_length = header[2]

        body = self.socket.recv(remaining_length)

        packet = header + body

        expected_cs = DeviceSocket.CalcChecksum(packet)
        packet_cs = packet[len(packet) - 1]
        if packet_cs != expected_cs:
            print(f"Bad checksum in device message? Saw {packet_cs:02x}, expected {expected_cs :02x}")
            DumpBuffer("packet", packet)
            return None

        return packet

    def Available(self, timeout = 0):
        if not self.socket:
            return False

        # Use select to check if there's data to read
        readable, _, _ = select.select([self.socket], [], [], timeout)
        return len(readable) > 0

class TempUnits(Enum):
    UNKNOWN = -1
    CELSIUS = 0
    FAHRENHEIT = 1

class TempDisplay(Enum):
    UNKNOWN = -1
    NONE = 0
    SETPOINT = 1
    INDOOR = 2
    OUTDOOR = 3

class DeviceMode(Enum):
    UNKNOWN = -1
    AUTO = 0
    COOL = 1    # 16
    DRY = 2     # 32
    FAN = 3     # 48
    HEAT = 4    # 64
    MODE5 = 5
    MODE6 = 6
    MODE7 = 7

class FanState(Enum):
    UNKNOWN = -1
    AUTO = 0
    LEVEL_1 = 1
    LEVEL_2 = 2
    LEVEL_3 = 3
    LEVEL_4 = 4
    LEVEL_5 = 5
    TURBO = 6
    QUIET = 7
    AUTO_QUIET = 8
    UNKNOWN_QUIET = 9

class ValveState(Enum):
    UNKNOWN = -1
    NONE = 0
    INTAKE = 1
    EXHAUST = 2
    OTHER = 3

class HumidifyType(Enum):
    UNKNOWN = -1
    NONE = 0
    CONTINUOUS = 1
    INTELLIGENT = 2
    LEVEL_40 = 3
    LEVEL_50 = 4
    LEVEL_60 = 5
    LEVEL_70 = 6

class SleepCurveType(Enum):
    UNKNOWN = -1
    NONE = 0
    EXPERT = 1
    TRADITIONAL = 2
    DIY = 3
    SIESTA = 128

class HorizontalAirDirection(Enum):
    UNKNOWN = 0
    SWINGING = 1
    LEFT = 2
    CENTER_LEFT = 3
    CENTER = 4
    CENTER_RIGHT = 5
    RIGHT = 6

class VerticalAirDirection(Enum):
    UNKNOWN = 0
    SWINGING = 1
    UP = 2
    CENTER_UP = 3
    CENTER = 4
    CENTER_DOWN = 5
    DOWN = 6

class DeviceConfig:
    def __init__(self):
        self.valid = False
        self.temp = -1
        self.temp_units = TempUnits.UNKNOWN
        self.is_on = False
        self.mode = DeviceMode.UNKNOWN
        self.light = False
        self.purify = False

        # Reported via status message if set via RF remote. Mobile app doesn't seem to set this.
        # Perhaps this can be set via on one of the unused bytes in the general command message.
        self.temp_display = TempDisplay.UNKNOWN

        # Sent using a secondary type of config message, but reported
        # via the general status message
        self.eco_mode = False

        # Top-level fan state, which unifies:
        # Speed / Quiet / Auto / Turbo
        # Generally, speed will be 0 (AUTO) if quiet or turbo are on
        self.fan_state = None   # None means 
        self.fan_speed = -1  # 0 = Auto
        self.turbo = False
        self.quiet_type = 0  # None, Auto, Quiet ?
        self.x_fan = False
        self.x_fan_for_heat = False
        self.intake_exhaust = ValveState.UNKNOWN
        self.fan_speed_low_res = 0  # Calculated from full speed when set?

        # Misc junk
        self.mode_mystery_bit_3 = False     # Passed back to device as-is
        self.mode_mystery_bit_2 = False     # Passed back to device as-is

        # Timer-related stuff
        self.timer_on_off_enable = False
        self.timer_on_enable = False
        self.timer_off_enable = False
        self.sleep_curve_clock_invalid = False
        self.clock = 0
        self.day_of_week = 0
        self.sleep_curve_clock = 0
        self.minutes_until_on = 0
        self.minutes_until_off = 0
        self.on_time = 0
        self.off_time = 0

        # 1 = use on time / off time for scheduling?
        # 0 = use countdown timers for scheduling?
        self.timer_on_use_clock = 0
        self.timer_off_use_clock = 0

        # Mon = 2, Tue = 4, Wed = 8, Thu = 10, Fri = 20, Sat = 40, Sun = 80
        self.day_of_week_on_mask = 0
        self.day_of_week_off_mask = 0

        self.horizontal_air_direction = HorizontalAirDirection.UNKNOWN
        self.vertical_air_direction = VerticalAirDirection.UNKNOWN

        # Untested; my unit lacks this feature
        self.humidify_type = HumidifyType.NONE
        self.heat_assist = False

        # Sleep curve stuff
        self.sleep_curve_type = SleepCurveType.NONE
        self.custom_sleep_curve = [0] * 8

        # Noise control
        self.noise_control_enable = False
        self.noise_control_heating = 30
        self.noise_control_cooling = 30

        # Region swing stuff, untested
        self.regional_swing_position = 0
        self.regional_swing_avoid_people = False

        # Determined experimentally
        self.use_remote_temp_sensor = False
        self.remote_temp_val = 0  # Seems to be in C, regardless of units?

        # Unknown
        self.timer_remote_flag = False

    def DecodeTemp(self, upper, lower):
        if self.temp_units == TempUnits.CELSIUS:
            return min(upper + 16, 30)

        if upper <= 0:
            return 61

        temp_f = ((upper + 16) * 9 / 5) + 32 + lower

        return min(int(temp_f), 86)

    def EncodeTemp(self, temp):
        if self.temp_units == TempUnits.CELSIUS:
            return int(temp) - 16

        temp_c = (temp - 32) / 9 * 5

        val = int(temp_c - 15.5)

        val = max(val, 0)
        val = min(val, 14)

        return val

    def EncodeTempFahrenheitFractionalBit(self, temp, units):
        if units == TempUnits.CELSIUS:
            return 0
        return temp in [63, 65, 67, 70, 72, 74, 76, 79, 81, 83, 85]

    def EncodeTempCelciusFractionalBit(self, temp, units):
        if units == TempUnits.CELSIUS:
            return (temp - int(temp)) == 0.5
        return 0

    def DecodeFanState(self, buf):
        if self.mode == DeviceMode.COOL or self.mode == DeviceMode.DRY:
            self.x_fan = GetBit(buf[10], 3)
            self.x_fan_for_heat = False

        if self.mode == DeviceMode.HEAT:
            self.x_fan  = 0
            self.x_fan_for_heat = GetBit(buf[10], 3)

        self.turbo = GetBit(buf[10], 0)
        self.quiet_type = GetBits(buf[20], 2, 2)
        self.intake_exhaust = ValveState(GetBits(buf[11], 4, 2))

        self.fan_speed = GetBits(buf[22], 0, 3)

        if self.turbo:
            self.fan_state = FanState.TURBO
        elif self.quiet_type == 1:
            self.fan_state = FanState.AUTO_QUIET
        elif self.quiet_type == 2:
            self.fan_state = FanState.QUIET
        elif self.quiet_type == 3:
            print(f"Unknown quiet_type: {self.quiet_type}")
        else:
            fan_speeds = [
                FanState.AUTO,
                FanState.LEVEL_1,
                FanState.LEVEL_2,
                FanState.LEVEL_3,
                FanState.LEVEL_4,
                FanState.LEVEL_5,
            ]
            if self.fan_speed >= 0 and self.fan_speed <= 5:
                self.fan_state = fan_speeds[self.fan_speed]
            else:
                self.fan_state = FanState.UNKNOWN

    def DecodeCustomSleepCurve(self, buf):
        self.custom_sleep_curve = [0] * 8
        self.custom_sleep_curve[0] = self.DecodeTemp(buf[21] >> 4, 0)
        self.custom_sleep_curve[1] = self.DecodeTemp(buf[21] & 0x0f, 0)
        self.custom_sleep_curve[2] = self.DecodeTemp(buf[24] >> 4, 0)
        self.custom_sleep_curve[3] = self.DecodeTemp(buf[24] & 0x0f, 0)
        self.custom_sleep_curve[4] = self.DecodeTemp(buf[25] >> 4, 0)
        self.custom_sleep_curve[5] = self.DecodeTemp(buf[25] & 0x0f, 0)
        self.custom_sleep_curve[6] = self.DecodeTemp(buf[26] >> 4, 0)
        self.custom_sleep_curve[7] = self.DecodeTemp(buf[26] & 0x0f, 0)

    def Decode(self, buf):
        if len(buf) < 51:
            print(f"Bad buffer length? {len(buf)}")
            return False

        self.is_on = GetBit(buf[8], 7)
        self.mode = DeviceMode(GetBits(buf[8], 4, 3))

        self.mode_mystery_bit_3 = GetBit(buf[8], 3)
        self.mode_mystery_bit_2 = GetBit(buf[8], 2)
        self.fan_speed_low_res = GetBits(buf[8], 0, 2)
        self.timer_on_off_enable = GetBit(buf[9], 3)

        temp_upper = GetBits(buf[9], 4, 4)
        temp_lower = GetBits(buf[11], 6, 1)
        if GetBits(buf[11], 7):
            self.temp_units = TempUnits.FAHRENHEIT
        else:
            self.temp_units = TempUnits.CELSIUS

        self.temp = self.DecodeTemp(temp_upper, temp_lower)

        if self.temp_units == TempUnits.CELSIUS and GetBit(buf[14], 3):
            self.temp += 0.5

        self.DecodeFanState(buf)

        self.purify = GetBit(buf[10], 2)
        self.light = GetBit(buf[10], 1)

        self.vertical_air_direction = VerticalAirDirection(GetBits(buf[12], 4, 4))
        self.horizontal_air_direction = HorizontalAirDirection(GetBits(buf[12], 0, 4))

        self.temp_display = TempDisplay(GetBits(buf[13], 4, 2))
        self.use_remote_temp_sensor = GetBit(buf[13], 6)

        self.humidify_type = HumidifyType(GetBits(buf[14], 4, 3))
        self.heat_assist = GetBit(buf[15], 7)

        # 16 17 18 - timer stuff

        self.minutes_until_on = ((buf[17] & 0x70) << 4) | buf[16]
        self.minutes_until_off = ((buf[18] & 0x7F) << 4) | (buf[17] & 0x0F)

        self.timer_remote_flag = GetBit(buf[17], 7)
        self.timer_on_enable = GetBit(buf[19], 5)
        self.timer_off_enable = GetBit(buf[19], 4)

        if GetBit(buf[20], 7):
            self.sleep_curve_type = SleepCurveType.SIESTA
        else:
            self.sleep_curve_type = SleepCurveType(((buf[8] & 0x08) >> 2) | ((buf[20] & 0x10) >> 4))


        self.DecodeCustomSleepCurve(buf)

        # Determined experimentally
        self.remote_temp_val = buf[28]

        self.clock = ((buf[29] & 0x7f) << 8) | buf[30]

        # Who knows?
        self.sleep_curve_clock_invalid = GetBit(buf[31], 7)
        self.sleep_curve_clock = ((buf[31] & 0x7f) << 8) | buf[32]

        self.timer_on_use_clock = GetBits(buf[33], 6, 2)
        self.timer_off_use_clock = GetBits(buf[33], 4, 2)

        self.off_time = ((buf[33] & 7) << 8) | buf[34]
        self.on_time = ((buf[35] & 7) << 8) | buf[36]

        self.day_of_week = GetBits(buf[35], 5, 3)

        # Bits 7-1; bit 0 is always 0?
        self.day_of_week_on_mask = buf[37]
        self.day_of_week_off_mask = buf[38]

        self.regional_swing_avoid_people = GetBit(buf[39], 2)

        if GetBit(buf[39], 1):
            self.regional_swing_position = 256
        else:
            self.regional_swing_position = buf[40]

        # Byte 41 is unused?

        self.noise_control_enable = GetBit(buf[42], 0)

        self.noise_control_cooling = buf[47]
        self.noise_control_heating = buf[48]
        self.eco_mode = GetBit(buf[49], 0)

        self.valid = True

        return True

    def Print(self):
        def format_time(t):
            return f"{int(t / 60):02}:{t % 60 :02}"

        print("\nGeneral:")

        if not self.valid:
            print("Uninitialized device config")
            return

        print(f"\tOn            :\t{self.is_on}")
        print(f"\tMode          :\t{self.mode}")
        print(f"\tTemp          :\t{self.temp}")
        print(f"\tUnits         :\t{self.temp_units}")
        print(f"\tTemp display  :\t{self.temp_display}")
        print(f"\tRemote sensor :\t{self.use_remote_temp_sensor} ({self.remote_temp_val} C)")
        print(f"\tLight         :\t{self.light}")
        print(f"\tPurify        :\t{self.purify}")
        print(f"\tHumidify      :\t{self.humidify_type}")
        print(f"\tHeat Assist   :\t{self.heat_assist}")
        print(f"\tEco mode:     :\t{self.eco_mode}")
        print(f"\tSleep curve   :\t{self.sleep_curve_type} {self.custom_sleep_curve}")
        print(f"\tH Direction   :\t{self.horizontal_air_direction}")
        print(f"\tV Direction   :\t{self.vertical_air_direction}")

        print("\nFan:")
        print(f"\tState :\t{self.fan_state}")
        print(f"\tSpeed :\t{self.fan_speed}")
        print(f"\tLowRes:\t{self.fan_speed_low_res}")
        print(f"\tTurbo :\t{self.turbo}")
        print(f"\tQuiet :\t{self.quiet_type}")
        print(f"\tValve :\t{self.intake_exhaust}")
        print(f"\tX-fan :\t{self.x_fan}")
        print(f"\tX-fan (Heat):\t{self.x_fan_for_heat}")

        print("\nTimers:")
        print(f"\tOn/off enabled             : {self.timer_on_off_enable}")
        print(f"\tOn enabled                 : {self.timer_on_enable}")
        print(f"\tOff enabled                : {self.timer_off_enable}")
        print(f"\tRemote flag                : {self.timer_remote_flag}")
        print(f"\tMinutes to on              : {self.minutes_until_on}")
        print(f"\tMinutes to off             : {self.minutes_until_off}")
        print(f"\tClock?                     : {self.clock:<4}\t{format_time(self.clock)}")
        print(f"\tDay of week                : {self.day_of_week}")
        print(f"\tOn time                    : {self.on_time:<4}\t{format_time(self.on_time)}")
        print(f"\tOff time                   : {self.off_time:<4}\t{format_time(self.off_time)}")
        print(f"\tSleep curve clock?         : {self.sleep_curve_clock:<4}\t{format_time(self.sleep_curve_clock)}")
        print(f"\tSleep curve clock valid?   : {self.sleep_curve_clock_invalid}")
        print(f"\tWeek day on mask           : 0x{self.day_of_week_on_mask:02x}")
        print(f"\tWeek day off mask          : 0x{self.day_of_week_off_mask:02x}")
        print(f"\tUse on time for schedule?  : {self.timer_on_use_clock}")
        print(f"\tUse off time for schedule? : {self.timer_off_use_clock}")

        print("\nNoise control:")
        print(f"\tEnabled   : {self.noise_control_enable}")
        print(f"\tIn heating : {self.noise_control_heating}")
        print(f"\tIn cooling : {self.noise_control_cooling}")

        print("\nRegional swing:")
        print(f"\tPersion position : {self.regional_swing_position}")
        print(f"\tAvoid people     : {self.regional_swing_avoid_people}")

    def Copy(self):
        return copy.deepcopy(self)

    def FanSpeedForNoiseLevel(self, noise_level):
        if noise_level >= 38:
            return 5
        
        if noise_level >= 36:
            return 4
        
        if noise_level >= 33:
            return 3
        
        if noise_level >= 31:
            return 2
        
        if noise_level >= 29:
            return 1

        return 0

    def Encode(self, update_on_off_timers = True):
        if not self.valid:
            return None

        cfg = self.Copy()
        out = [0x00] * 40
        out[0] = 0x7E
        out[1] = 0x7E
        out[2] = len(out) - 3
        out[3] = 0x01

        # Suspect that this is a bitmask of settings to update. Conjecture:
        # Bit 7 = ?
        # Bit 6 = Update remote temperature setting ("FOLLOW ME")
        # Bit 5 = ?
        # Bit 4 = ?
        # Bit 3 = ?
        # Bit 2 = ?
        # Bit 1 = Update on/off timer values (minutes to on/off)
        # Bit 0 = ?
        # The app hard-codes this to AF, but the remote sends either 85 or 87 when FOLLOW ME ("I FEEL") is off, and C5
        # when FOLLOW ME is on. So, maybe bit 6 represents whether the external temp sensor value needs to be updated?
        out[4] = 0xAD

        # Don't update on/off timers unless requested, to avoid clock drift assocaited with
        # quantizing to the nearest minute.
        # Determined partly experimentally; remote sends 85 for normal updates and 87 if on/off
        # times have changed. Interestingly, despite having an RTC, the remote still uses the
        # timers (rather than the on time / off time) for scheduling.
        if update_on_off_timers:
            out[4] |= 0x02

        # If we are telling the unit to send a new "I FEEL" temperature, set the bit that causes the unit to latch the
        # new "I FEEL" value. This needs to be done *in addition to* the bit that actually enables the "I FEEL" feature.
        if self.use_remote_temp_sensor:
            out[4] |= 0x40  # Also update the remote temp reading?

        # If not on, disable a handful of secondary things
        if not cfg.is_on:
            cfg.intake_exhaust = ValveState.NONE
            cfg.quiet_type = 0
            cfg.sleep_curve_type = SleepCurveType.NONE
            cfg.humidify_type = HumidifyType.NONE
            cfg.purify = 0

        # If we have a top-level fan state (which unifies Quiet, Turbo, and fan speed), use that
        # to set all the other fan parameters
        if cfg.fan_state is not None:
            cfg.turbo = False
            cfg.quiet_type = 0
            cfg.fan_speed = 0

            if cfg.fan_state == FanState.TURBO:
                cfg.turbo = True

            # In the mobile app, "Quiet" sets quiet_type to 2 and "Auto quiet" sets it to 1.
            # "Quiet" on the RF remote seems to set quiet_type to 2.
            # Annoyingly, quiet_type is not the same as noise control. The latter seems to be
            # just a naive mechanism for limiting the commanded fan speed, and doesn't affect the
            # quiet_type setting?
            if cfg.fan_state == FanState.AUTO_QUIET:
                cfg.quiet_type = 1

            # The app seems to prefer this
            if cfg.fan_state == FanState.QUIET:
                cfg.quiet_type = 2

            # One of the vanilla states? Translate it directly
            if cfg.fan_state in [FanState.AUTO, FanState.LEVEL_1, FanState.LEVEL_2, FanState.LEVEL_3, FanState.LEVEL_4, FanState.LEVEL_5]:
                cfg.fan_speed = cfg.fan_state.value

        # Why even bother? Why does the unit even need to know the desired noise control levels,
        # if these are handled entirely by limiting the fan speed? Maybe this is what the other
        # quiet_type values are for?
        if cfg.noise_control_enable:
            if cfg.mode == DeviceMode.HEAT:
                cfg.fan_speed = self.FanSpeedForNoiseLevel(self.noise_control_heating)
                cfg.turbo = False

            if cfg.mode == DeviceMode.COOL:
                cfg.fan_speed = self.FanSpeedForNoiseLevel(self.noise_control_cooling)
                cfg.turbo = False

        # Ugh. Guessing this is the "low-res" (?) version of fan speed, perhaps made for
        # backwards compatibility, back when they only supported three fan speeds.
        # We'll set the fan speed as-is (in all its 5-level glory) in a different byte later on.
        out[5] = ((cfg.fan_speed + 1) >> 1) | (cfg.is_on << 7) | (cfg.mode.value << 4)
        out[5] |= ((cfg.sleep_curve_type.value & 2) << 2) | (cfg.mode_mystery_bit_2 << 2)
        out[6] = (cfg.EncodeTemp(cfg.temp) << 4) | (cfg.timer_on_off_enable << 3)

        out[7] = (cfg.purify << 2) | (cfg.light << 1) | (cfg.turbo << 0)

        # Only enable X-Fan in cool/dehumidify modes
        # X-fan runs the blower for several minutes after cool/dehimidify is turned off, to dry
        # the coils and presumably prevent mold growth?
        if cfg.mode == DeviceMode.COOL or cfg.mode == DeviceMode.DRY:
            out[7] |= (cfg.x_fan << 3)

        # Not sure what the X-Fan-for-heat bit does. Maybe some other feature entirely?
        # I think this may be one of the ways "e-heater" is enabled
        if cfg.mode == DeviceMode.HEAT:
            out[7] |= (cfg.x_fan_for_heat << 3)

        out[8] = (cfg.EncodeTempFahrenheitFractionalBit(cfg.temp, cfg.temp_units) << 6)
        out[8] |= ((cfg.temp_units == TempUnits.FAHRENHEIT) << 7)
        out[8] |= (cfg.intake_exhaust.value << 4)
        out[8] |= 0x02  # App hardcodes this; no idea what it does
        out[9] = (cfg.vertical_air_direction.value << 4) | cfg.horizontal_air_direction.value

        # Determined experimentally
        out[10] = (cfg.temp_display.value << 4) | (cfg.use_remote_temp_sensor << 6)

        out[11] = (cfg.EncodeTempCelciusFractionalBit(cfg.temp, cfg.temp_units) << 3) | (cfg.humidify_type.value << 4)

        if cfg.mode == DeviceMode.HEAT:
            out[12] = cfg.heat_assist << 7

        out[13] = cfg.minutes_until_on & 0xff
        out[14] = ((cfg.minutes_until_on & 0x700) >> 4) | (cfg.minutes_until_off & 0x0f) | (cfg.timer_remote_flag << 7)
        out[15] = (cfg.minutes_until_off & 0x7f0) >> 4

        out[16] = (cfg.timer_on_enable << 5) | (cfg.timer_off_enable << 4)

        out[17] = cfg.quiet_type << 2
    
        # The sleep curve type is encoded in a silly way
        if cfg.sleep_curve_type == SleepCurveType.SIESTA:
            out[17] |= cfg.sleep_curve_type.value
        else:
            out[17] |= (cfg.sleep_curve_type.value & 1) << 4

        out[18] = (cfg.EncodeTemp(cfg.custom_sleep_curve[0]) << 4) | cfg.EncodeTemp(cfg.custom_sleep_curve[1])
        out[19] = cfg.fan_speed

        # Putting some non-zero values here causes "EY" to be displayed on the unit
        # This means "outdoor ambient temperature reading out of range". Does this let us override
        # the outdoor temperature reading??
        out[20] = 0

        out[21] = (cfg.EncodeTemp(cfg.custom_sleep_curve[2]) << 4) | cfg.EncodeTemp(cfg.custom_sleep_curve[3])
        out[22] = (cfg.EncodeTemp(cfg.custom_sleep_curve[4]) << 4) | cfg.EncodeTemp(cfg.custom_sleep_curve[5])
        out[23] = (cfg.EncodeTemp(cfg.custom_sleep_curve[6]) << 4) | cfg.EncodeTemp(cfg.custom_sleep_curve[7])

        # Bytes 24 and 25 are fixed at 0?
        # It looks like byte 25 might provide a way to specify the value of the remote temp
        # reading. This value is briefly reported in the remote temp sensor field of the status
        # packet, but is soon overwritten by the most recent reading actually received from the
        # remote. This seems to happen even if the I FEEL / FOLLOW ME function of the remote is
        # off.
        out[25] = cfg.remote_temp_val  # Remote temp sensor, in C??

        out[26] = cfg.clock >> 8
        out[27] = cfg.clock & 0xff

        out[28] = cfg.sleep_curve_clock >> 8
        out[29] = cfg.sleep_curve_clock & 0xff

        out[30] = (cfg.timer_on_use_clock << 6) | (cfg.timer_off_use_clock << 4) | (cfg.off_time >> 8)
        out[31] = cfg.off_time & 0xff

        out[32] = (cfg.day_of_week << 5) | (cfg.on_time >> 8)
        out[33] = cfg.on_time & 0xff

        out[34] = cfg.day_of_week_on_mask
        out[35] = cfg.day_of_week_off_mask

        out[36] = (cfg.regional_swing_avoid_people << 1)

        # A position of 256 seems to spill over into a different byte
        if cfg.regional_swing_position == 256:
            out[36] |= 0x01
        else:
            out[37] = cfg.regional_swing_position

        self.SetChecksum(out)

        return out


    def EncodeRemoteTempUpdate(self):
        if not self.valid:
            return None

        cfg = self.Copy()
        out = [0x00] * 40
        out[0] = 0x7E
        out[1] = 0x7E
        out[2] = len(out) - 3
        out[3] = 0x01

        # If we are telling the unit to send a new "I FEEL" temperature, set the bit that causes the unit to latch the
        # new "I FEEL" value. This needs to be done *in addition to* the bit that actually enables the "I FEEL" feature.
        if self.use_remote_temp_sensor:
            out[4] |= 0x40  # Also update the remote temp reading?

        out[25] = cfg.remote_temp_val  # Remote temp sensor, in C??

        self.SetChecksum(out)
        return out


    def SetChecksum(self, buf):
        sum = 0
        for i in range(2, len(buf) - 1):
            sum += buf[i]
        buf[len(buf) - 1] = sum & 0xff

sock = DeviceSocket()
sock.Open()

cfg = DeviceConfig()

sent = False

while True:
    time.sleep(1)
    sock.SendQuery()

    while sock.Available(0.1):
        buf = sock.Read()
        DumpBuffer("receive", buf)

        if buf is None:
            print("Invalid frame received?")
            continue

        if buf[3] == 0x31 or buf[3] == 0x32:  # Query response?
            cfg.Decode(buf)
            cfg.Print()
        else:
            print(f"Unknown frame received: 0x{buf[3]:02x}")
            DumpBuffer("unknown frame", buf)
            continue

    cmd = cfg.Encode()
    DumpBuffer("config", cmd)

    # Hack, for initial testing. After receiving the first status message, send a test config.
    if cfg.valid and not sent:
        cfg.noise_control_enable = False
        cfg.fan_state = FanState.LEVEL_5
        cfg.mode = DeviceMode.HEAT
        cfg.temp_units = TempUnits.FAHRENHEIT
        cfg.is_on = True
        cfg.temp = 72  # Set point
        cfg.temp_display = TempDisplay.NONE
        cfg.remote_temp_val = 25  # Always in C
        cfg.use_remote_temp_sensor = False

        # Seems to be set by unit, regardless of what we do?
        cfg.timer_remote_flag = False

        # Test: turn on the heat to 74F, for ten minutes, then turn off
        cfg.timer_on_off_enable = True
        cfg.timer_off_enable = True
        cfg.timer_on_enable = False
        cfg.minutes_until_on = 0
        cfg.minutes_until_off = 10
        cfg.vertical_air_direction = VerticalAirDirection.CENTER_DOWN
        sock.SendConfig(cfg)

        sent = True
