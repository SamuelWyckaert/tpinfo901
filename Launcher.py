from threading import Thread
from time import sleep
from typing import List

from Process import Process


def launch(nbProcessToCreate: int, runningTime: int):

    def createProcess(x: int):
        processes.append(Process("P" + str(x), nbProcessToCreate))

    processes = []

    processes_launches: List[Thread] = []

    for k in range(nbProcessToCreate):
        processes_launches.append(Thread(target=createProcess, args=(k,)))

    for process in processes_launches:
        process.start()
    for process in processes_launches:
        process.join()

    sleep(runningTime)

    for process in processes:
        process.stop()



if __name__ == '__main__':
    launch(3, 5)
