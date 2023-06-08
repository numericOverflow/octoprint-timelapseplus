from ..constants import Constants


class StabilizationHelper:

    def __init__(self, settings, stabilizationSettings):
        self.SNAPSHOT_COMMAND = settings.get(["snapshotCommand"])
        self.STAB = stabilizationSettings

    def getRetractionCommands(self, positionTracker, inverse):
        shouldDoRetract = self.STAB.RETRACT_AMOUNT > 0 or self.STAB.RETRACT_Z_HOP > 0
        if not shouldDoRetract:
            return []

        cmd = []

        cmd += self.getCommandsPositionRelative(positionTracker.RELATIVE_MODE, positionTracker.RELATIVE_MODE_EXTRUDER, True, True)

        if inverse:
            cmd.append('G1 E' + str(self.STAB.RETRACT_AMOUNT) + ' F' + str(self.STAB.getFeedrateRetraction()))
            cmd.append('G1 Z-' + str(self.STAB.RETRACT_Z_HOP) + ' F' + str(self.STAB.getFeedrateMove()))
        else:
            cmd.append('G1 E-' + str(self.STAB.RETRACT_AMOUNT) + ' F' + str(self.STAB.getFeedrateRetraction()))
            cmd.append('G1 Z' + str(self.STAB.RETRACT_Z_HOP) + ' F' + str(self.STAB.getFeedrateMove()))

        cmd += self.getCommandsPositionRelative(True, True, positionTracker.RELATIVE_MODE, positionTracker.RELATIVE_MODE_EXTRUDER)

        return cmd

    def getCommandsPositionRelative(self, fromValMove, fromValExt, toValMove, toValExt):
        cmd = []

        if toValMove != fromValMove:
            if toValMove:
                cmd.append('G91')
                if Constants.GCODE_G90_G91_EXTRUDER_OVERWRITE:
                    fromValExt = True
            else:
                cmd.append('G90')
                fromValExt = False

        if toValExt != fromValExt:
            if toValExt:
                cmd.append('M83')
                isRelE = True
            else:
                cmd.append('M82')
                isRelE = False

        return cmd

    def getMoveCommands(self, positionTracker, x, y, z, f):
        cmd = []

        cmd += self.getCommandsPositionRelative(positionTracker.RELATIVE_MODE, positionTracker.RELATIVE_MODE_EXTRUDER, False, positionTracker.RELATIVE_MODE_EXTRUDER)

        cmd.append('G0 X' + str(x) + ' Y' + str(y) + ' Z' + str(z) + ' F' + str(f))

        self.getCommandsPositionRelative(False, positionTracker.RELATIVE_MODE_EXTRUDER, positionTracker.RELATIVE_MODE, positionTracker.RELATIVE_MODE_EXTRUDER)

        return cmd

    def stabilizeAndQueueSnapshotRaw(self, printer, positionTracker):
        if printer.set_job_on_hold(True):

            newZPos = self.STAB.PARK_Z
            if self.STAB.PARK_Z_RELATIVE:
                newZPos = positionTracker.POS_Z + self.STAB.PARK_Z

            cmd = []
            try:
                cmd += self.getRetractionCommands(positionTracker, False)
                cmd += self.getMoveCommands(positionTracker, self.STAB.PARK_X, self.STAB.PARK_Y, newZPos, self.STAB.getFeedrateMove())

                if self.STAB.WAIT_FOR_MOVEMENT:
                    cmd.append('M400')

                if self.STAB.WAIT_BEFORE > 0:
                    cmd.append('G4 P' + str(self.STAB.WAIT_BEFORE))

                cmd.append('@' + self.SNAPSHOT_COMMAND + '-' + Constants.SUFFIX_PRINT_UNSTABLE)

                if self.STAB.WAIT_AFTER > 0:
                    cmd.append('G4 P' + str(self.STAB.WAIT_AFTER))

                cmd += self.getMoveCommands(positionTracker, positionTracker.POS_X, positionTracker.POS_Y, positionTracker.POS_Z, self.STAB.getFeedrateMove())
                cmd += self.getRetractionCommands(positionTracker, True)

                printer.commands(cmd, force=True, tags={Constants.GCODE_TAG_STABILIZATION})

                # TODO Update PositionTracker with the created Commands
            finally:
                printer.set_job_on_hold(False)
