# Copyright (c) Jeroen Van Steirteghem
# See LICENSE

import asyncio
import base64
import json
import socket
import struct
import twunnel3.logger
import twunnel3.proxy_server

def set_default_configuration(configuration, keys):
    twunnel3.proxy_server.set_default_configuration(configuration, keys)
    
    if "LOCAL_PROXY_SERVER" in keys:
        configuration.setdefault("LOCAL_PROXY_SERVER", {})
        configuration["LOCAL_PROXY_SERVER"].setdefault("TYPE", "")
        if configuration["LOCAL_PROXY_SERVER"]["TYPE"] == "HTTPS":
            configuration["LOCAL_PROXY_SERVER"].setdefault("ADDRESS", "")
            configuration["LOCAL_PROXY_SERVER"].setdefault("PORT", 0)
        else:
            if configuration["LOCAL_PROXY_SERVER"]["TYPE"] == "SOCKS4":
                configuration["LOCAL_PROXY_SERVER"].setdefault("ADDRESS", "")
                configuration["LOCAL_PROXY_SERVER"].setdefault("PORT", 0)
            else:
                if configuration["LOCAL_PROXY_SERVER"]["TYPE"] == "SOCKS5":
                    configuration["LOCAL_PROXY_SERVER"].setdefault("ADDRESS", "")
                    configuration["LOCAL_PROXY_SERVER"].setdefault("PORT", 0)
                    configuration["LOCAL_PROXY_SERVER"].setdefault("ACCOUNTS", [])
                    i = 0
                    while i < len(configuration["LOCAL_PROXY_SERVER"]["ACCOUNTS"]):
                        configuration["LOCAL_PROXY_SERVER"]["ACCOUNTS"][i].setdefault("NAME", "")
                        configuration["LOCAL_PROXY_SERVER"]["ACCOUNTS"][i].setdefault("PASSWORD", "")
                        i = i + 1

class OutputProtocol(asyncio.Protocol):
    def __init__(self):
        twunnel3.logger.log(3, "trace: OutputProtocol.__init__")
        
        self.input_protocol = None
        self.connection_state = 0
        self.transport = None
        
    def connection_made(self, transport):
        twunnel3.logger.log(3, "trace: OutputProtocol.connection_made")
        
        self.transport = transport
        
        self.connection_state = 1
        
        self.input_protocol.output_protocol__connection_made(self.transport)
        
    def connection_lost(self, exception):
        twunnel3.logger.log(3, "trace: OutputProtocol.connection_lost")
        
        self.connection_state = 2
        
        self.input_protocol.output_protocol__connection_lost(exception)
        
        self.transport = None
        
    def data_received(self, data):
        twunnel3.logger.log(3, "trace: OutputProtocol.data_received")
        
        self.input_protocol.output_protocol__data_received(data)
        
    def input_protocol__connection_made(self, transport):
        twunnel3.logger.log(3, "trace: OutputProtocol.input_protocol__connection_made")
        
    def input_protocol__connection_lost(self, exception):
        twunnel3.logger.log(3, "trace: OutputProtocol.input_protocol__connection_lost")
        
        if self.connection_state == 1:
            self.transport.close()
        
    def input_protocol__data_received(self, data):
        twunnel3.logger.log(3, "trace: OutputProtocol.input_protocol__data_received")
        
        if self.connection_state == 1:
            self.transport.write(data)
    
    def pause_writing(self):
        twunnel3.logger.log(3, "trace: OutputProtocol.pause_reading")
        
        if self.connection_state == 1:
            self.transport.pause_reading()
    
    def resume_writing(self):
        twunnel3.logger.log(3, "trace: OutputProtocol.resume_writing")
        
        if self.connection_state == 1:
            self.transport.resume_reading()

class OutputProtocolFactory(object):
    def __init__(self, input_protocol):
        twunnel3.logger.log(3, "trace: OutputProtocolFactory.__init__")
        
        self.input_protocol = input_protocol
        
    def __call__(self):
        twunnel3.logger.log(3, "trace: OutputProtocolFactory.__call__")
        
        output_protocol = OutputProtocol()
        output_protocol.input_protocol = self.input_protocol
        output_protocol.input_protocol.output_protocol = output_protocol
        return output_protocol

class HTTPSInputProtocol(asyncio.Protocol):
    def __init__(self):
        twunnel3.logger.log(3, "trace: HTTPSInputProtocol.__init__")
        
        self.configuration = None
        self.output_protocol = None
        self.remote_address = ""
        self.remote_port = 0
        self.connection_state = 0
        self.data = b""
        self.data_state = 0
        self.transport = None
    
    def connection_made(self, transport):
        twunnel3.logger.log(3, "trace: HTTPSInputProtocol.connection_made")
        
        self.transport = transport
        
        self.connection_state = 1
    
    def connection_lost(self, exception):
        twunnel3.logger.log(3, "trace: HTTPSInputProtocol.connection_lost")
        
        self.connection_state = 2
        
        if self.output_protocol is not None:
            self.output_protocol.input_protocol__connection_lost(exception)
        
        self.transport = None
    
    def data_received(self, data):
        twunnel3.logger.log(3, "trace: HTTPSInputProtocol.data_received")
        
        self.data = self.data + data
        if self.data_state == 0:
            if self.process_data_state0():
                return
        if self.data_state == 1:
            if self.process_data_state1():
                return
    
    def process_data_state0(self):
        twunnel3.logger.log(3, "trace: HTTPSInputProtocol.process_data_state0")
        
        data = self.data
        
        i = data.find(b"\r\n\r\n")
        
        if i == -1:
            return True
        
        i = i + 4
        
        request = data[:i]
        
        data = data[i:]
        
        self.data = data
        
        request_lines = request.split(b"\r\n")
        request_line = request_lines[0].split(b" ", 2)
        
        if len(request_line) != 3:
            response = b"HTTP/1.1 400 Bad Request\r\n"
            response = response + b"\r\n"
            
            self.transport.write(response)
            self.transport.close()
            
            return True
        
        request_method = request_line[0].upper()
        request_uri = request_line[1]
        request_version = request_line[2].upper()
        
        if request_method == b"CONNECT":
            address = b""
            port = 0
            
            i1 = request_uri.find(b"[")
            i2 = request_uri.find(b"]")
            i3 = request_uri.rfind(b":")
            
            if i3 > i2:
                address = request_uri[:i3]
                port = int(request_uri[i3 + 1:])
            else:
                address = request_uri
                port = 443
            
            if i2 > i1:
                address = address[i1 + 1:i2]
            
            self.remote_address = address.decode()
            self.remote_port = port
            
            twunnel3.logger.log(2, "remote_address: " + self.remote_address)
            twunnel3.logger.log(2, "remote_port: " + str(self.remote_port))
            
            output_protocol_factory = OutputProtocolFactory(self)
            
            tunnel = twunnel3.proxy_server.create_tunnel(self.configuration)
            asyncio.async(tunnel.create_connection(output_protocol_factory, self.remote_address, self.remote_port))
            
            return True
        else:
            response = b"HTTP/1.1 405 Method Not Allowed\r\n"
            response = response + b"Allow: CONNECT\r\n"
            response = response + b"\r\n"
            
            self.transport.write(response)
            self.transport.close()
            
            return True
        
    def process_data_state1(self):
        twunnel3.logger.log(3, "trace: HTTPSInputProtocol.process_data_state1")
        
        self.output_protocol.input_protocol__data_received(self.data)
        
        self.data = b""
        
        return True
        
    def output_protocol__connection_made(self, transport):
        twunnel3.logger.log(3, "trace: HTTPSInputProtocol.output_protocol__connection_made")
        
        if self.connection_state == 1:
            response = b"HTTP/1.1 200 OK\r\n"
            response = response + b"\r\n"
            
            self.transport.write(response)
            
            self.output_protocol.input_protocol__connection_made(self.transport)
            if len(self.data) > 0:
                self.output_protocol.input_protocol__data_received(self.data)
            
            self.data = b""
            self.data_state = 1
        else:
            if self.connection_state == 2:
                self.output_protocol.input_protocol__connection_lost(None)
        
    def output_protocol__connection_lost(self, exception):
        twunnel3.logger.log(3, "trace: HTTPSInputProtocol.output_protocol__connection_lost")
        
        if self.connection_state == 1:
            if self.data_state == 1:
                self.transport.close()
            else:
                response = b"HTTP/1.1 404 Not Found\r\n"
                response = response + b"\r\n"
                
                self.transport.write(response)
                self.transport.close()
        else:
            if self.connection_state == 2:
                self.output_protocol.input_protocol__connection_lost(None)
        
    def output_protocol__data_received(self, data):
        twunnel3.logger.log(3, "trace: HTTPSInputProtocol.output_protocol__data_received")
        
        if self.connection_state == 1:
            self.transport.write(data)
        else:
            if self.connection_state == 2:
                self.output_protocol.input_protocol__connection_lost(None)
    
    def pause_writing(self):
        twunnel3.logger.log(3, "trace: HTTPSInputProtocol.pause_reading")
        
        if self.connection_state == 1:
            self.transport.pause_reading()
    
    def resume_writing(self):
        twunnel3.logger.log(3, "trace: HTTPSInputProtocol.resume_writing")
        
        if self.connection_state == 1:
            self.transport.resume_reading()

class HTTPSInputProtocolFactory(object):
    protocol = HTTPSInputProtocol
    
    def __init__(self, configuration):
        twunnel3.logger.log(3, "trace: HTTPSInputProtocolFactory.__init__")
        
        self.configuration = configuration
    
    def __call__(self):
        twunnel3.logger.log(3, "trace: HTTPSInputProtocolFactory.__call__")
        
        input_protocol = HTTPSInputProtocol()
        input_protocol.configuration = self.configuration
        return input_protocol

class SOCKS4InputProtocol(asyncio.Protocol):
    def __init__(self):
        twunnel3.logger.log(3, "trace: SOCKS4InputProtocol.__init__")
        
        self.configuration = None
        self.output_protocol = None
        self.remote_address = ""
        self.remote_port = 0
        self.connection_state = 0
        self.data = b""
        self.data_state = 0
        self.transport = None
    
    def connection_made(self, transport):
        twunnel3.logger.log(3, "trace: SOCKS4InputProtocol.connection_made")
        
        self.transport = transport
        
        self.connection_state = 1
    
    def connection_lost(self, exception):
        twunnel3.logger.log(3, "trace: SOCKS4InputProtocol.connection_lost")
        
        self.connection_state = 2
        
        if self.output_protocol is not None:
            self.output_protocol.input_protocol__connection_lost(exception)
        
        self.transport = None
    
    def data_received(self, data):
        twunnel3.logger.log(3, "trace: SOCKS4InputProtocol.data_received")
        
        self.data = self.data + data
        if self.data_state == 0:
            if self.process_data_state0():
                return
        if self.data_state == 1:
            if self.process_data_state1():
                return
        
    def process_data_state0(self):
        twunnel3.logger.log(3, "trace: SOCKS4InputProtocol.process_data_state0")
        
        data = self.data
        
        if len(data) < 8:
            return True
        
        version, method, port, address = struct.unpack("!BBHI", data[:8])
        
        data = data[8:]
        
        address_type = 0x01
        if address >= 1 and address <= 255:
            address_type = 0x03
        
        self.remote_port = port
        
        if address_type == 0x01:
            address = struct.pack("!I", address)
            address = socket.inet_ntop(socket.AF_INET, address)
            
            self.remote_address = address
        
        if b"\x00" not in data:
            return True
        
        name, data = data.split(b"\x00", 1)
        
        if address_type == 0x03:
            if b"\x00" not in data:
                return True
            
            address, data = data.split(b"\x00", 1)
            
            self.remote_address = address.decode()
        
        self.data = data
        
        twunnel3.logger.log(2, "remote_address: " + self.remote_address)
        twunnel3.logger.log(2, "remote_port: " + str(self.remote_port))
        
        if method == 0x01:
            output_protocol_factory = OutputProtocolFactory(self)
            
            tunnel = twunnel3.proxy_server.create_tunnel(self.configuration)
            asyncio.async(tunnel.create_connection(output_protocol_factory, self.remote_address, self.remote_port))
            
            return True
        else:
            response = struct.pack("!BBHI", 0x00, 0x5b, 0, 0)
            
            self.transport.write(response)
            self.transport.close()
            
            return True
        
    def process_data_state1(self):
        twunnel3.logger.log(3, "trace: SOCKS4InputProtocol.process_data_state1")
        
        self.output_protocol.input_protocol__data_received(self.data)
        
        self.data = b""
        
        return True
        
    def output_protocol__connection_made(self, transport):
        twunnel3.logger.log(3, "trace: SOCKS4InputProtocol.output_protocol__connection_made")
        
        if self.connection_state == 1:
            response = struct.pack("!BBHI", 0x00, 0x5a, 0, 0)
            
            self.transport.write(response)
            
            self.output_protocol.input_protocol__connection_made(self.transport)
            if len(self.data) > 0:
                self.output_protocol.input_protocol__data_received(self.data)
            
            self.data = b""
            self.data_state = 1
        else:
            if self.connection_state == 2:
                self.output_protocol.input_protocol__connection_lost(None)
    
    def output_protocol__connection_lost(self, exception):
        twunnel3.logger.log(3, "trace: SOCKS4InputProtocol.output_protocol__connection_lost")
        
        if self.connection_state == 1:
            if self.data_state != 1:
                response = struct.pack("!BBHI", 0x00, 0x5b, 0, 0)
                
                self.transport.write(response)
                self.transport.close()
            else:
                self.transport.close()
        else:
            if self.connection_state == 2:
                self.output_protocol.input_protocol__connection_lost(None)
        
    def output_protocol__data_received(self, data):
        twunnel3.logger.log(3, "trace: SOCKS4InputProtocol.output_protocol__data_received")
        
        if self.connection_state == 1:
            self.transport.write(data)
        else:
            if self.connection_state == 2:
                self.output_protocol.input_protocol__connection_lost(None)
    
    def pause_writing(self):
        twunnel3.logger.log(3, "trace: SOCKS4InputProtocol.pause_reading")
        
        if self.connection_state == 1:
            self.transport.pause_reading()
    
    def resume_writing(self):
        twunnel3.logger.log(3, "trace: SOCKS4InputProtocol.resume_writing")
        
        if self.connection_state == 1:
            self.transport.resume_reading()

class SOCKS4InputProtocolFactory(object):
    def __init__(self, configuration):
        twunnel3.logger.log(3, "trace: SOCKS4InputProtocolFactory.__init__")
        
        self.configuration = configuration
    
    def __call__(self):
        twunnel3.logger.log(3, "trace: SOCKS4InputProtocolFactory.__call__")
        
        input_protocol = SOCKS4InputProtocol()
        input_protocol.configuration = self.configuration
        return input_protocol

class SOCKS5InputProtocol(asyncio.Protocol):
    def __init__(self):
        twunnel3.logger.log(3, "trace: SOCKS5InputProtocol.__init__")
        
        self.configuration = None
        self.output_protocol = None
        self.remote_address = ""
        self.remote_port = 0
        self.connection_state = 0
        self.data = b""
        self.data_state = 0
        self.transport = None
    
    def connection_made(self, transport):
        twunnel3.logger.log(3, "trace: SOCKS5InputProtocol.connection_made")
        
        self.transport = transport
        
        self.connection_state = 1
    
    def connection_lost(self, exception):
        twunnel3.logger.log(3, "trace: SOCKS5InputProtocol.connection_lost")
        
        self.connection_state = 2
        
        if self.output_protocol is not None:
            self.output_protocol.input_protocol__connection_lost(exception)
        
        self.transport = None
    
    def data_received(self, data):
        twunnel3.logger.log(3, "trace: SOCKS5InputProtocol.data_received")
        
        self.data = self.data + data
        if self.data_state == 0:
            if self.process_data_state0():
                return
        if self.data_state == 1:
            if self.process_data_state1():
                return
        if self.data_state == 2:
            if self.process_data_state2():
                return
        if self.data_state == 3:
            if self.process_data_state3():
                return
    
    def process_data_state0(self):
        twunnel3.logger.log(3, "trace: SOCKS5InputProtocol.process_data_state0")
        
        data = self.data
        
        if len(data) < 2:
            return True
        
        version, number_of_methods = struct.unpack("!BB", data[:2])
        
        data = data[2:]
        
        if len(data) < number_of_methods:
            return True
        
        methods = struct.unpack("!%dB" % number_of_methods, data[:number_of_methods])
        
        data = data[number_of_methods:]
        
        self.data = data
        
        supported_methods = []
        if len(self.configuration["LOCAL_PROXY_SERVER"]["ACCOUNTS"]) == 0:
            supported_methods.append(0x00)
        else:
            supported_methods.append(0x02)
        
        for supported_method in supported_methods:
            if supported_method in methods:
                if supported_method == 0x00:
                    response = struct.pack("!BB", 0x05, 0x00)
                    
                    self.transport.write(response)
                    
                    self.data_state = 2
                    
                    return False
                else:
                    if supported_method == 0x02:
                        response = struct.pack("!BB", 0x05, 0x02)
                        
                        self.transport.write(response)
                        
                        self.data_state = 1
                        
                        return True
        
        response = struct.pack("!BB", 0x05, 0xFF)
        
        self.transport.write(response)
        self.transport.close()
        
        return True
        
    def process_data_state1(self):
        twunnel3.logger.log(3, "trace: SOCKS5InputProtocol.process_data_state1")
        
        data = self.data
        
        if len(data) < 2:
            return True
        
        version, name_length = struct.unpack("!BB", data[:2])
        
        data = data[2:]
        
        if len(data) < name_length:
            return True
        
        name, = struct.unpack("!%ds" % name_length, data[:name_length])
        
        data = data[name_length:]
        
        if len(data) < 1:
            return True
        
        password_length, = struct.unpack("!B", data[:1])
        
        data = data[1:]
        
        if len(data) < password_length:
            return True
        
        password, = struct.unpack("!%ds" % password_length, data[:password_length])
        
        data = data[password_length:]
        
        self.data = data
        
        i = 0
        while i < len(self.configuration["LOCAL_PROXY_SERVER"]["ACCOUNTS"]):
            if self.configuration["LOCAL_PROXY_SERVER"]["ACCOUNTS"][i]["NAME"].encode() == name:
                if self.configuration["LOCAL_PROXY_SERVER"]["ACCOUNTS"][i]["PASSWORD"].encode() == password:
                    response = struct.pack("!BB", 0x05, 0x00)
                    
                    self.transport.write(response)
                    
                    self.data_state = 2
                    
                    return True
                
                response = struct.pack("!BB", 0x05, 0x01)
                
                self.transport.write(response)
                self.transport.close()
                
                return True
            
            i = i + 1
        
        response = struct.pack("!BB", 0x05, 0x01)
        
        self.transport.write(response)
        self.transport.close()
        
        return True
        
    def process_data_state2(self):
        twunnel3.logger.log(3, "trace: SOCKS5InputProtocol.process_data_state2")
        
        data = self.data
        
        if len(data) < 4:
            return True
        
        version, method, reserved, address_type = struct.unpack("!BBBB", data[:4])
        
        data = data[4:]
        
        if address_type == 0x01:
            if len(data) < 4:
                return True
            
            address, = struct.unpack("!I", data[:4])
            address = struct.pack("!I", address)
            address = socket.inet_ntop(socket.AF_INET, address)
            
            self.remote_address = address
            
            data = data[4:]
        else:
            if address_type == 0x03:
                if len(data) < 1:
                    return True
                
                address_length, = struct.unpack("!B", data[:1])
                
                data = data[1:]
                
                if len(data) < address_length:
                    return True
                
                address, = struct.unpack("!%ds" % address_length, data[:address_length])
                
                self.remote_address = address.decode()
                
                data = data[address_length:]
            else:
                if address_type == 0x04:
                    if len(data) < 16:
                        return True
                    
                    address1, address2, address3, address4 = struct.unpack("!IIII", data[:16])
                    address = struct.pack("!IIII", address1, address2, address3, address4)
                    address = socket.inet_ntop(socket.AF_INET6, address)
                    
                    self.remote_address = address
                    
                    data = data[16:]
        
        if len(data) < 2:
            return True
        
        port, = struct.unpack("!H", data[:2])
        
        self.remote_port = port
        
        data = data[2:]
        
        self.data = data
        
        twunnel3.logger.log(2, "remote_address: " + self.remote_address)
        twunnel3.logger.log(2, "remote_port: " + str(self.remote_port))
        
        if method == 0x01:
            output_protocol_factory = OutputProtocolFactory(self)
            
            tunnel = twunnel3.proxy_server.create_tunnel(self.configuration)
            asyncio.async(tunnel.create_connection(output_protocol_factory, self.remote_address, self.remote_port))
            
            return True
        else:
            response = struct.pack("!BBBBIH", 0x05, 0x07, 0x00, 0x01, 0, 0)
            
            self.transport.write(response)
            self.transport.close()
            
            return True
        
    def process_data_state3(self):
        twunnel3.logger.log(3, "trace: SOCKS5InputProtocol.process_data_state3")
        
        self.output_protocol.input_protocol__data_received(self.data)
        
        self.data = b""
        
        return True
        
    def output_protocol__connection_made(self, transport):
        twunnel3.logger.log(3, "trace: SOCKS5InputProtocol.output_protocol__connection_made")
        
        if self.connection_state == 1:
            response = struct.pack("!BBBBIH", 0x05, 0x00, 0x00, 0x01, 0, 0)
            
            self.transport.write(response)
            
            self.output_protocol.input_protocol__connection_made(self.transport)
            if len(self.data) > 0:
                self.output_protocol.input_protocol__data_received(self.data)
            
            self.data = b""
            self.data_state = 3
        else:
            if self.connection_state == 2:
                self.output_protocol.input_protocol__connection_lost(None)
        
    def output_protocol__connection_lost(self, exception):
        twunnel3.logger.log(3, "trace: SOCKS5InputProtocol.output_protocol__connection_lost")
        
        if self.connection_state == 1:
            if self.data_state != 3:
                response = struct.pack("!BBBBIH", 0x05, 0x05, 0x00, 0x01, 0, 0)
                
                self.transport.write(response)
                self.transport.close()
            else:
                self.transport.close()
        else:
            if self.connection_state == 2:
                self.output_protocol.input_protocol__connection_lost(None)
        
    def output_protocol__data_received(self, data):
        twunnel3.logger.log(3, "trace: SOCKS5InputProtocol.output_protocol__data_received")
        
        if self.connection_state == 1:
            self.transport.write(data)
        else:
            if self.connection_state == 2:
                self.output_protocol.input_protocol__connection_lost(None)
    
    def pause_writing(self):
        twunnel3.logger.log(3, "trace: SOCKS5InputProtocol.pause_reading")
        
        if self.connection_state == 1:
            self.transport.pause_reading()
    
    def resume_writing(self):
        twunnel3.logger.log(3, "trace: SOCKS5InputProtocol.resume_writing")
        
        if self.connection_state == 1:
            self.transport.resume_reading()

class SOCKS5InputProtocolFactory(object):
    def __init__(self, configuration):
        twunnel3.logger.log(3, "trace: SOCKS5InputProtocolFactory.__init__")
        
        self.configuration = configuration
    
    def __call__(self):
        twunnel3.logger.log(3, "trace: SOCKS5InputProtocolFactory.buildProtocol")
        
        input_protocol = SOCKS5InputProtocol()
        input_protocol.configuration = self.configuration
        return input_protocol

def get_input_protocol_factory_class(type):
    if type == "HTTPS":
        return HTTPSInputProtocolFactory
    else:
        if type == "SOCKS4":
            return SOCKS4InputProtocolFactory
        else:
            if type == "SOCKS5":
                return SOCKS5InputProtocolFactory
            else:
                return None

def create_server(configuration):
    set_default_configuration(configuration, ["PROXY_SERVERS", "LOCAL_PROXY_SERVER"])
    
    input_protocol_factory_class = get_input_protocol_factory_class(configuration["LOCAL_PROXY_SERVER"]["TYPE"])
    input_protocol_factory = input_protocol_factory_class(configuration)
    return asyncio.get_event_loop().create_server(input_protocol_factory, host=configuration["LOCAL_PROXY_SERVER"]["ADDRESS"], port=configuration["LOCAL_PROXY_SERVER"]["PORT"])