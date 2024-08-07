import dbus
import dbus.exceptions
import dbus.mainloop.glib
import dbus.service

try:
    from gi.repository import GLib
except ImportError:
    import gobject as GLib
import sys
import pynmea2
import threading
import time
import serial
# ... (existing imports and constants)

# Global variables for GPS data
LATITUDE = 37.7749  # Default: San Francisco
LONGITUDE = -122.4194
gps_lock = threading.Lock()

# ... (existing classes: InvalidArgsException, NotSupportedException, Application, Service)


BLUEZ_SERVICE_NAME = 'org.bluez'
LE_ADVERTISING_MANAGER_IFACE = 'org.bluez.LEAdvertisingManager1'
DBUS_OM_IFACE = 'org.freedesktop.DBus.ObjectManager'
DBUS_PROP_IFACE = 'org.freedesktop.DBus.Properties'

GATT_MANAGER_IFACE = 'org.bluez.GattManager1'
GATT_SERVICE_IFACE = 'org.bluez.GattService1'
GATT_CHRC_IFACE = 'org.bluez.GattCharacteristic1'
AGENT_IFACE = 'org.bluez.Agent1'
AGENT_MANAGER_IFACE = 'org.bluez.AgentManager1'
ADAPTER_IFACE = 'org.bluez.Adapter1'

# Fixed location values
LATITUDE = 37.7749  # Example: San Francisco
LONGITUDE = -122.4194

class InvalidArgsException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.freedesktop.DBus.Error.InvalidArgs'

class NotSupportedException(dbus.exceptions.DBusException):
    _dbus_error_name = 'org.bluez.Error.NotSupported'

class Application(dbus.service.Object):
    def __init__(self, bus):
        self.path = '/'
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service(self, service):
        self.services.append(service)

    @dbus.service.method(DBUS_OM_IFACE, out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        response = {}
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            chrcs = service.get_characteristics()
            for chrc in chrcs:
                response[chrc.get_path()] = chrc.get_properties()
        return response

class Service(dbus.service.Object):
    PATH_BASE = '/org/bluez/example/service'

    def __init__(self, bus, index, uuid, primary):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.uuid = uuid
        self.primary = primary
        self.characteristics = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_SERVICE_IFACE: {
                'UUID': self.uuid,
                'Primary': self.primary,
                'Characteristics': dbus.Array(
                    self.get_characteristic_paths(),
                    signature='o')
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_characteristic(self, characteristic):
        self.characteristics.append(characteristic)

    def get_characteristic_paths(self):
        result = []
        for chrc in self.characteristics:
            result.append(chrc.get_path())
        return result

    def get_characteristics(self):
        return self.characteristics

    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_SERVICE_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_SERVICE_IFACE]

class Characteristic(dbus.service.Object):
    def __init__(self, bus, index, uuid, flags, service):
        self.path = service.path + '/char' + str(index)
        self.bus = bus
        self.uuid = uuid
        self.service = service
        self.flags = flags
        self.descriptors = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_CHRC_IFACE: {
                'Service': self.service.get_path(),
                'UUID': self.uuid,
                'Flags': self.flags,
                'Descriptors': dbus.Array(
                    self.get_descriptor_paths(),
                    signature='o')
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_descriptor(self, descriptor):
        self.descriptors.append(descriptor)

    def get_descriptor_paths(self):
        result = []
        for desc in self.descriptors:
            result.append(desc.get_path())
        return result

    def get_descriptors(self):
        return self.descriptors

    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != GATT_CHRC_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[GATT_CHRC_IFACE]

    @dbus.service.method(GATT_CHRC_IFACE,
                        in_signature='a{sv}',
                        out_signature='ay')
    def ReadValue(self, options):
        print('Default ReadValue called, returning error')
        raise NotSupportedException()

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='aya{sv}')
    def WriteValue(self, value, options):
        print('Default WriteValue called, returning error')
        raise NotSupportedException()

    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        print('Default StartNotify called, returning error')
        raise NotSupportedException()

    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        print('Default StopNotify called, returning error')
        raise NotSupportedException()

    @dbus.service.signal(DBUS_PROP_IFACE,
                         signature='sa{sv}as')
    def PropertiesChanged(self, interface, changed, invalidated):
        pass

class LocationCharacteristic(Characteristic):
    def __init__(self, bus, index, service):
        Characteristic.__init__(
            self, bus, index,
            '87654321-1234-5678-1234-56789abcdef0',
            ['read', 'notify'],
            service)
        self.notifying = False
        GLib.timeout_add(1000, self.notify_location)

    def get_location(self):
        global LATITUDE, LONGITUDE
        with gps_lock:
            value = f"{LATITUDE},{LONGITUDE}".encode()
        return value

    def ReadValue(self, options):
        print('LocationCharacteristic Read: ' + repr(self.get_location()))
        return self.get_location()

    def StartNotify(self):
        if self.notifying:
            print('Already notifying, nothing to do')
            return
        self.notifying = True

    def StopNotify(self):
        if not self.notifying:
            print('Not notifying, nothing to do')
            return
        self.notifying = False

    def notify_location(self):
        if not self.notifying:
            return True
        self.PropertiesChanged(
            GATT_CHRC_IFACE,
            {'Value': self.get_location()}, [])
        return True

# ... (existing classes: LocationService, Agent, Advertisement)

def read_gps_data():
    global LATITUDE, LONGITUDE
    ser = serial.Serial('/dev/serial0', 9600, timeout=1)  # Adjust port as needed
    while True:
        try:
            line = ser.readline().decode('ascii', errors='replace')
            if line.startswith('$GPGGA'):
                msg = pynmea2.parse(line)
                with gps_lock:
                    LATITUDE = msg.latitude
                    LONGITUDE = msg.longitude
                print(f"Updated GPS: {LATITUDE}, {LONGITUDE}")
        except Exception as e:
            print(f"Error reading GPS: {e}")
        time.sleep(1)

class LocationService(Service):
    def __init__(self, bus, index):
        Service.__init__(self, bus, index, '12345678-1234-5678-1234-56789abcdef0', True)
        self.add_characteristic(LocationCharacteristic(bus, 0, self))

class Agent(dbus.service.Object):
    AGENT_PATH = "/test/agent"

    def __init__(self, bus):
        dbus.service.Object.__init__(self, bus, self.AGENT_PATH)

    @dbus.service.method(AGENT_IFACE, in_signature='', out_signature='')
    def Release(self):
        print("Release")

    @dbus.service.method(AGENT_IFACE, in_signature='o', out_signature='')
    def RequestAuthorization(self, device):
        print(f"RequestAuthorization ({device})")

    @dbus.service.method(AGENT_IFACE, in_signature='os', out_signature='')
    def AuthorizeService(self, device, uuid):
        print(f"AuthorizeService ({device}, {uuid})")

    @dbus.service.method(AGENT_IFACE, in_signature='o', out_signature='')
    def Cancel(self, device):
        print(f"Cancel ({device})")

class Advertisement(dbus.service.Object):
    PATH_BASE = '/org/bluez/example/advertisement'

    def __init__(self, bus, index, advertising_type):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.ad_type = advertising_type
        self.service_uuids = None
        self.manufacturer_data = None
        self.solicit_uuids = None
        self.service_data = None
        self.include_tx_power = False
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        properties = dict()
        properties['Type'] = self.ad_type
        if self.service_uuids:
            properties['ServiceUUIDs'] = dbus.Array(self.service_uuids, signature='s')
        if self.solicit_uuids:
            properties['SolicitUUIDs'] = dbus.Array(self.solicit_uuids, signature='s')
        if self.manufacturer_data:
            properties['ManufacturerData'] = dbus.Dictionary(self.manufacturer_data, signature='qv')
        if self.service_data:
            properties['ServiceData'] = dbus.Dictionary(self.service_data, signature='sv')
        properties['IncludeTxPower'] = self.include_tx_power
        return {LE_ADVERTISING_MANAGER_IFACE: properties}

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='s',
                         out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != LE_ADVERTISING_MANAGER_IFACE:
            raise InvalidArgsException()
        return self.get_properties()[LE_ADVERTISING_MANAGER_IFACE]

    @dbus.service.method(DBUS_PROP_IFACE,
                         in_signature='',
                         out_signature='')
    def Release(self):
        pass

def find_adapter(bus):
    remote_om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, '/'),
                               DBUS_OM_IFACE)
    objects = remote_om.GetManagedObjects()
    for path, interfaces in objects.items():
        if ADAPTER_IFACE in interfaces:
            return path
    return None

def register_app_cb():
    print('GATT application registered')

def register_app_error_cb(error):
    print(f'Failed to register application: {error}')
    mainloop.quit()

def register_ad_cb():
    print('Advertisement registered')

def register_ad_error_cb(error):
    print(f'Failed to register advertisement: {error}')
    mainloop.quit()

def main():
    global mainloop
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    adapter = find_adapter(bus)
    if not adapter:
        print('LEAdvertisingManager1 interface not found')
        return

    service_manager = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE_NAME, adapter),
        GATT_MANAGER_IFACE)

    app = Application(bus)
    location_service = LocationService(bus, 0)
    app.add_service(location_service)

    mainloop = GLib.MainLoop()

    agent_manager = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, "/org/bluez"), AGENT_MANAGER_IFACE)
    agent = Agent(bus)
    agent_manager.RegisterAgent(Agent.AGENT_PATH, "NoInputNoOutput")
    agent_manager.RequestDefaultAgent(Agent.AGENT_PATH)

    print('Registering GATT application...')

    service_manager.RegisterApplication(app.get_path(), {},
                                        reply_handler=register_app_cb,
                                        error_handler=register_app_error_cb)

    # BLE Advertisement setup
    ad_manager = dbus.Interface(
        bus.get_object(BLUEZ_SERVICE_NAME, adapter),
        LE_ADVERTISING_MANAGER_IFACE)

    advertisement = Advertisement(bus, 0, 'peripheral')
    advertisement.service_uuids = ['12345678-1234-5678-1234-56789abcdef0']  # Example Service UUID
    ad_manager.RegisterAdvertisement(advertisement.get_path(), {},
                                     reply_handler=register_ad_cb,
                                     error_handler=register_ad_error_cb)

    # Start GPS reading thread
    gps_thread = threading.Thread(target=read_gps_data, daemon=True)
    gps_thread.start()

    mainloop.run()

if __name__ == '__main__':
    main()
