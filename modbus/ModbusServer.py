import asyncio
import logging
from threading import Thread

from pymodbus.datastore import ModbusSlaveContext
from pymodbus.datastore.context import ModbusServerContext
from pymodbus.device import ModbusDeviceIdentification
from pymodbus.server import ModbusTcpServer

from mca.communication import ModbusData


class NWHSModbusServer:
    def __init__(self, data: ModbusData, logger=logging.getLogger(__name__)):
        self.data = data
        self.log = logger
        self._started = False
        # TODO: pull from config
        self.identity = ModbusDeviceIdentification(
            info_name={
                "VendorName": "Pymodbus",
                "ProductCode": "PM",
                "VendorUrl": "https://github.com/pymodbus-dev/pymodbus/",
                "ProductName": "Pymodbus Server",
                "ModelName": "Pymodbus Server",
                "MajorMinorRevision": "0.0.1",
            }
        )

        self.context = ModbusServerContext(
            slaves=ModbusSlaveContext(
                di=self.data,  # pyright: ignore
                co=self.data,  # pyright: ignore
                hr=self.data,  # pyright: ignore
                ir=self.data,  # pyright: ignore due to inheritance
            ),
            single=True,
        )

        # NOTE: can take an address if needed later
        # start with self.server.serve_forever()
        #
        self.loop = None
        self.server = None
        self.thread: Thread = Thread(target=self.run)
        self._running = False
        self.result = None
        self.task = None
        self.address = ("", 50502)

    def start(self):
        self.log.info("starting start")
        if not self.thread.is_alive():
            self.log.info("starting thread.start")
            self.thread.start()
        self.log.info(f"start done {self.thread} {self.task}")

    def run(self):
        self.log.info("starting run")
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.log.info("run starting loop")

        self.task = self.loop.create_task(self.serve())
        self.log.info(f"added task {self.task} ")
        self.loop.run_forever()
        self.loop.close()

        self.log.info(f"run completed {self.result}")

    async def serve(self):
        self.log.info("starting serve")
        self.server = ModbusTcpServer(
            context=self.context, identity=self.identity, address=self.address
        )
        await self.server.serve_forever()
        self.log.info(f"done serve {self.server}")

    async def disconnect(self) -> bool:
        if self.server:
            self.shutdown = await self.server.shutdown()
        return not self.running()

    def running(self) -> bool:
        if self.thread is None or self.loop is None:
            self.log.info("modbus not running yet")
            return False

        alive: bool = self.thread.is_alive()
        running = self.loop.is_running()
        tasks = asyncio.all_tasks(self.loop)

        status: bool = self.data.status()
        self.log.debug(f"modbus running status a{alive} r{running} t{tasks} ")

        return alive and running and status
