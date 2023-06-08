import os.path
from threading import Thread


class InfillFinder:
    def __init__(self, gcodeFile, settings):
        self.FILE = gcodeFile
        self.INFILL_BLOCKS = []
        self.SNAPSHOTS = []
        self.SNAPSHOT_COMMAND = settings.get(["snapshotCommand"])

    def getNextInfillPosition(self, position):
        allInfillBlocksAfter = [x for x in self.INFILL_BLOCKS if x[0] > position]
        nextInfillBlock = min(allInfillBlocksAfter, key=lambda x: x[0])

        allSnapshotPositionsAfter = [x for x in self.SNAPSHOTS if x > position]
        nextSnapshotPos = min(allSnapshotPositionsAfter)

        # Position is in the 'middle' of the infill
        blockFrom = nextInfillBlock[0]
        blockTo = min(nextInfillBlock[1], nextSnapshotPos)
        blockRange = blockTo - blockFrom
        return blockFrom + int(blockRange / 2)

    def canQueueSnapshotAt(self, position):
        if position is None:
            return False

        hasInfillAfter = any(x[0] > position for x in self.INFILL_BLOCKS)
        if not hasInfillAfter:
            return False

        allSnapshotPositionsAfter = [x for x in self.SNAPSHOTS if x > position]
        nextSnapshotPos = min(allSnapshotPositionsAfter)

        allInfillBlocksAfter = [x for x in self.INFILL_BLOCKS if x[0] > position]
        nextInfillBlock = min(allInfillBlocksAfter, key=lambda x: x[0])

        return nextInfillBlock[0] < nextSnapshotPos

    def startScanFile(self):
        if not os.path.isfile(self.FILE):
            return

        Thread(target=self.scanFile, daemon=True).start()

    def scanFile(self):
        lastInfillStart = None

        position = 0
        with open(self.FILE, 'r') as file:
            for line in file:
                position = position + len(line)
                line = line.strip()

                if self.isLineSnapshot(line):
                    self.SNAPSHOTS.append(position)
                    continue

                if lastInfillStart is None and self.isLineStartInfill(line):
                    lastInfillStart = position
                if lastInfillStart is not None and self.isLineEndInfill(line):
                    self.INFILL_BLOCKS.append((lastInfillStart, position))
                    lastInfillStart = None

        print('INFILL SCAN DONE')

    def isLineSnapshot(self, line):
        parts = line.split(';', 1)
        return parts[0].strip().upper() == '@' + self.SNAPSHOT_COMMAND.strip().upper()

    def isLineStartInfill(self, line):
        return line == ';TYPE:Internal infill'

    def isLineEndInfill(self, line):
        return line.startswith(';TYPE:') and not self.isLineStartInfill(line)
