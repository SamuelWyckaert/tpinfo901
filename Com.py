import random
from time import sleep
from typing import Callable, List

from Mailbox import Mailbox

from pyeventbus3.pyeventbus3 import PyBus, subscribe, Mode

from Message import *

class Com:

    def __init__(self, nbProcess):
        self.nbProcess = nbProcess
        self.myId = None
        self.listInitId = []

        self.aliveProcesses = []
        self.maybeAliveProcesses = []

        PyBus.Instance().register(self, self)
        sleep(1)

        self.mailbox = Mailbox()
        self.clock = 0

        self.nbSync = 0
        self.isSyncing = False

        self.tokenState = TokenState.Null
        self.currentTokenId = None

        self.isBlocked = False
        self.awaitingFrom = []
        self.recvObj = None

        self.alive = True
        if self.getMyId() == self.nbProcess - 1:
            self.currentTokenId = random.randint(0, 10000 * (self.nbProcess - 1))
            self.sendToken()

    def getNbProcess(self) -> int:

        return self.nbProcess

    def getMyId(self) -> int:
 
        if self.myId is None:
            self.initMyId()
        return self.myId

    def initMyId(self):
        randomNumber = random.randint(0, 100000 * (self.nbProcess - 1))
        print(self, ["random id:", randomNumber])
        self.sendMessage(InitIdMessage(randomNumber))
        sleep(2)
        if len(set(self.listInitId)) != self.nbProcess:
            print("rety")
            self.listInitId = []
            return self.initMyId()
        self.listInitId.sort()
        self.myId = self.listInitId.index(randomNumber)
        print("id :", self.myId, "list :", self.listInitId, "random :", randomNumber,)

    @subscribe(threadMode=Mode.PARALLEL, onEvent=InitIdMessage)
    def onReceiveInitIdMessage(self, message: InitIdMessage):

        print("Received init id message with random equal to", message.getObject())
        self.listInitId.append(message.getObject())

    def sendMessage(self, message: Message):

        if not message.is_system:
            self.incClock()
            message.horloge = self.clock
        print(message)
        PyBus.Instance().post(message)

    def sendTo(self, obj: any, com_to: int):

        self.sendMessage(MessageTo(obj, self.getMyId(), com_to))

    @subscribe(threadMode=Mode.PARALLEL, onEvent=MessageTo)
    def onReceive(self, message: MessageTo):

        if message.to_id != self.getMyId() or type(message) in [MessageToSync, Token, AcknowledgementMessage]:
            return
        if not message.is_system:
            self.clock = max(self.clock, message.horloge) + 1
        print("Received MessageTo from", message.from_id, ":", message.getObject())
        self.mailbox.addMessage(message)

    def sendToSync(self, obj: any, com_to: int):

        self.awaitingFrom = com_to
        self.sendMessage(MessageToSync(obj, self.getMyId(), com_to))
        while com_to == self.awaitingFrom:
            if not self.alive:
                return

    def recevFromSync(self, com_from: int) -> any:

        self.awaitingFrom = com_from
        while com_from == self.awaitingFrom:
            if not self.alive:
                return
        ret = self.recvObj
        self.recvObj = None
        return ret

    @subscribe(threadMode=Mode.PARALLEL, onEvent=MessageToSync)
    def onReceiveSync(self, message: MessageToSync):

        if message.to_id != self.getMyId():
            return
        if not message.is_system:
            self.clock = max(self.clock, message.horloge) + 1
        while message.from_id != self.awaitingFrom:
            if not self.alive:
                return
        self.awaitingFrom = -1
        self.recvObj = message.getObject()
        self.sendMessage(AcknowledgementMessage(self.getMyId(), message.from_id))

    def broadcastSync(self, com_from: int, obj: any = None) -> any:

        if self.getMyId() == com_from:
            print("Broadcasting synchroneously", obj)
            for i in range(self.nbProcess):
                if i != self.getMyId():
                    self.sendToSync(obj, i, 99)
        else:
            return self.recevFromSync(com_from)

    @subscribe(threadMode=Mode.PARALLEL, onEvent=AcknowledgementMessage)
    def onAckSync(self, event: AcknowledgementMessage):

        if self.getMyId() == event.to_id:
            print("Received AcknowledgementMessage from", event.from_id)
            self.awaitingFrom = -1

    def synchronize(self):

        self.isSyncing = True
        print("Synchronizing")
        while self.isSyncing:
            sleep(0.1)
            print("Synchronizing in")
            if not self.alive:
                return
        while self.nbSync != 0:
            sleep(0.1)
            print("Synchronizing out")
            if not self.alive:
                return
        print("Synchronized")

    def requestSC(self):

        print("Requesting SC")
        self.tokenState = TokenState.Requested
        while self.tokenState == TokenState.Requested:
            if not self.alive:
                return
        print("Received SC")

    def broadcast(self, obj: any):

        self.sendMessage(BroadcastMessage(obj, self.getMyId()))

    @subscribe(threadMode=Mode.PARALLEL, onEvent=BroadcastMessage)
    def onBroadcast(self, message: BroadcastMessage):

        if message.from_id == self.getMyId():
            return
        print("Received broadcasted message from", message.from_id, ":", message.getObject())
        if not message.is_system:
            self.clock = max(self.clock, message.horloge) + 1
        self.mailbox.addMessage(message)

    def sendToken(self):

        if self.currentTokenId is None:
            return
        sleep(0.1)
        self.sendMessage(Token(self.getMyId(), (self.getMyId() + 1) % self.nbProcess, self.nbSync, self.currentTokenId))
        self.currentTokenId = None

    def releaseSC(self):

        print("Releasing SC")
        if self.tokenState == TokenState.SC:
            self.tokenState = TokenState.Release
        self.sendToken()
        self.tokenState = TokenState.Null
        print("Released SC")

    def incClock(self):

        self.clock += 1

    def getClock(self) -> int:

        return self.clock

    def stop(self):

        self.alive = False

    @subscribe(threadMode=Mode.PARALLEL, onEvent=Token)
    def onToken(self, event: Token):

        if event.to_id != self.getMyId() or not self.alive:
            return
        print("token from", event.from_id)
        self.currentTokenId = event.currentTokenId
        self.nbSync = event.nbSync + int(self.isSyncing)% self.nbProcess
        self.isSyncing = False
        if self.tokenState == TokenState.Requested:
            self.tokenState = TokenState.SC
        else:
            self.sendToken()

    def doCriticalAction(self, funcToCall: Callable, *args: List[any]) -> any:

        self.requestSC()
        ret = None
        if self.alive:
            if args is None:
                ret = funcToCall()
            else:
                ret = funcToCall(*args)
            self.releaseSC()
        return ret
