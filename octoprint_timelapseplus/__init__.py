import base64
import glob
import io
import os
import random
import string
from threading import Thread
from time import sleep

from PIL import Image

import octoprint.plugin
from octoprint.events import Events
from .apiController import ApiController
from .model.captureMode import CaptureMode
from .model.enhancementPreset import EnhancementPreset
from .model.frameZip import FrameZip
from .model.mask import Mask
from .model.printJob import PrintJob
from .model.renderJob import RenderJob
from .model.renderJobState import RenderJobState
from .model.renderPreset import RenderPreset
from .model.video import Video


class TimelapsePlusPlugin(
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.EventHandlerPlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.BlueprintPlugin
):
    def __init__(self):
        super().__init__()
        self.PRINTJOB = None
        self.RENDERJOBS = []

    @octoprint.plugin.BlueprintPlugin.route("/createBlurMask", methods=["POST"])
    def apiCreateBlurMask(self):
        return self.API_CONTROLLER.createBlurMask()

    @octoprint.plugin.BlueprintPlugin.route("/getData", methods=["POST"])
    def apiGetData(self):
        self.sendClientData()
        return self.API_CONTROLLER.emptyResponse()

    @octoprint.plugin.BlueprintPlugin.route("/defaultEnhancementPreset", methods=["POST"])
    def apiDefaultEnhancementPreset(self):
        return EnhancementPreset(self).getJSON()

    @octoprint.plugin.BlueprintPlugin.route("/getRenderPresetVideoLength", methods=["POST"])
    def apiGetRenderPresetVideoLength(self):
        return self.API_CONTROLLER.getRenderPresetVideoLength()

    @octoprint.plugin.BlueprintPlugin.route("/defaultRenderPreset", methods=["POST"])
    def apiDefaultRenderPreset(self):
        return RenderPreset().getJSON()

    @octoprint.plugin.BlueprintPlugin.route("/delete", methods=["POST"])
    def apiDelete(self):
        self.API_CONTROLLER.delete()
        return self.API_CONTROLLER.emptyResponse()

    @octoprint.plugin.BlueprintPlugin.route("/listPresets", methods=["POST"])
    def apiListPresets(self):
        return self.API_CONTROLLER.listPresets()

    @octoprint.plugin.BlueprintPlugin.route("/render", methods=["POST"])
    def apiRender(self):
        self.API_CONTROLLER.render()
        return self.API_CONTROLLER.emptyResponse()

    @octoprint.plugin.BlueprintPlugin.route("/thumbnail", methods=["GET"])
    def apiThumbnail(self):
        return self.API_CONTROLLER.thumbnail()

    @octoprint.plugin.BlueprintPlugin.route("/maskPreview", methods=["GET"])
    def apiMaskPreview(self):
        return self.API_CONTROLLER.maskPreview()

    @octoprint.plugin.BlueprintPlugin.route("/download", methods=["GET"])
    def apiDownload(self):
        return self.API_CONTROLLER.download()

    @octoprint.plugin.BlueprintPlugin.route("/enhancementPreview", methods=["GET"])
    def apiEnhancementPreview(self):
        return self.API_CONTROLLER.enhancementPreview()

    def makeThumbnail(self, img, size=(320, 180)):
        img.thumbnail(size)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=50)
        byteArr = buf.getvalue()
        return byteArr

    def get_assets(self):
        return {
            'js': ['js/timelapseplus.js'],
            'less': [],
            'css': ['css/timelapseplus.css'],
        }

    def get_template_configs(self):
        return [
            {
                "type": "tab",
                "template": "timelapseplus_tab.jinja2",
                "div": "timelapseplus",
                "custom_bindings": True,
            },
            {
                "type": "settings",
                "template": "timelapseplus_settings.jinja2",
                "custom_bindings": False
            }
        ]

    def get_settings_defaults(self):
        return dict(
            captureMode=CaptureMode.COMMAND.name,
            captureTimerInterval=10,
            snapshotCommand="SNAPSHOT",
            renderAfterPrint=True,
            enhancementPresets=[EnhancementPreset(self).getJSON()],
            renderPresets=[RenderPreset().getJSON()]
        )

    def get_template_vars(self):
        epRaw = self._settings.get(["enhancementPresets"])
        epList = list(map(lambda x: EnhancementPreset(self, x), epRaw))
        epNew = list(map(lambda x: x.getJSON(), epList))

        rpRaw = self._settings.get(["renderPresets"])
        rpList = list(map(lambda x: RenderPreset(x), rpRaw))
        rpNew = list(map(lambda x: x.getJSON(), rpList))

        return dict(
            captureMode=self._settings.get(["captureMode"]),
            captureTimerInterval=self._settings.get(["captureTimerInterval"]),
            snapshotCommand=self._settings.get(["snapshotCommand"]),
            renderAfterPrint=self._settings.get(["renderAfterPrint"]),
            enhancementPresets=epNew,
            renderPresets=rpNew
        )

    def listFrameZips(self):
        files = glob.glob(self._settings.getBaseFolder('timelapse') + '/*.zip')
        frameZips = list(map(lambda x: FrameZip(x, self, self._logger), files))
        frameZips.sort(key=lambda x: x.TIMESTAMP)
        frameZips.reverse()
        return frameZips

    def listVideos(self):
        files = glob.glob(self._settings.getBaseFolder('timelapse') + '/*.mp4')
        videos = list(map(lambda x: Video(x, self, self._logger), files))
        videos.sort(key=lambda x: x.TIMESTAMP)
        videos.reverse()
        return videos

    def sendClientData(self):
        data = dict(
            isRunning=False,
            currentFileSize=0,
            captureMode=None,
            captureTimerInterval=0,
            snapshotCommand=self._settings.get(["snapshotCommand"]),
            snapshotCount=0,
            previewImage=None,
            frameCollections=list(map(lambda x: x.getJSON(), self.listFrameZips())),
            renderJobs=list(map(lambda x: x.getJSON(), self.RENDERJOBS)),
            videos=list(map(lambda x: x.getJSON(), self.listVideos()))
        )

        if self.PRINTJOB is not None:
            data['currentFileSize'] = self.PRINTJOB.getTotalFileSize()
            data['captureMode'] = self.PRINTJOB.CAPTURE_MODE.name
            data['captureTimerInterval'] = self.PRINTJOB.CAPTURE_TIMER_INTERVAL

            if len(self.PRINTJOB.FRAMES) > 0:
                with open(self.PRINTJOB.FRAMES[-1], 'rb') as image_file:
                    imgBytes = image_file.read()
                    img = Image.open(io.BytesIO(imgBytes))
                    thumb = self.makeThumbnail(img, (640, 360))
                    data['previewImage'] = base64.b64encode(thumb)

            data['isRunning'] = self.PRINTJOB.RUNNING
            data['snapshotCount'] = len(self.PRINTJOB.FRAMES)

        self._plugin_manager.send_plugin_message(self._identifier, data)

    def getRandomString(self, length):
        return ''.join(random.choice(string.ascii_uppercase + string.digits) for i in range(length))

    def on_after_startup(self):
        self.API_CONTROLLER = ApiController(self, self._data_folder, self._settings)

    def renderJobStateChanged(self, job, state):
        self.sendClientData()

        if state == RenderJobState.FINISHED or state == RenderJobState.FAILED:
            Thread(target=(lambda j: (
                sleep(10),
                self.RENDERJOBS.remove(j),
                self.sendClientData()
            )), args=(job,)).start()

    def renderJobProgressChanged(self, job, progress):
        self.sendClientData()

    def doneSnapshot(self):
        self.sendClientData()

    def atCommand(self, comm, phase, command, parameters, tags=None, *args, **kwargs):
        if self.PRINTJOB is None or not self.PRINTJOB.RUNNING:
            return

        if command != self._settings.get(["snapshotCommand"]):
            return

        if self.PRINTJOB.CAPTURE_MODE != CaptureMode.COMMAND:
            return

        self.PRINTJOB.doSnapshot()

    def atAction(self, comm, line, action, *args, **kwargs):
        if self.PRINTJOB is None or not self.PRINTJOB.RUNNING:
            return

        if action != self._settings.get(["snapshotCommand"]):
            return

        if self.PRINTJOB.CAPTURE_MODE != CaptureMode.COMMAND:
            return

        self.PRINTJOB.doSnapshot()

    def render(self, frameZip, enhancementPreset=None, renderPreset=None):
        job = RenderJob(frameZip, self, self._logger, self._settings, self._data_folder, enhancementPreset, renderPreset)
        job.start()
        self.RENDERJOBS.append(job)

    def printStarted(self):
        if self.PRINTJOB is not None and self.PRINTJOB.RUNNING:
            return

        printerFile = self._printer.get_current_job()['file']['path']
        baseName = os.path.splitext(os.path.basename(printerFile))[0]

        self.PRINTJOB = PrintJob(baseName, self, self._logger, self._settings, self._data_folder)
        self.PRINTJOB.start()
        self.sendClientData()

    def printFinished(self, success):
        if self.PRINTJOB is None or not self.PRINTJOB.RUNNING:
            return

        zipFileName = self.PRINTJOB.finish()
        self.sendClientData()

        if self._settings.get(["renderAfterPrint"]):
            if zipFileName != None:
                frameZip = FrameZip(zipFileName, self, self._logger)
                self.render(frameZip)

    def printPaused(self):
        if self.PRINTJOB is None or not self.PRINTJOB.RUNNING:
            return

        self.PRINTJOB.PAUSED = True

    def printResumed(self):
        if self.PRINTJOB is None or not self.PRINTJOB.RUNNING:
            return

        self.PRINTJOB.PAUSED = False

    def on_event(self, event, payload):
        if event == Events.PRINT_STARTED:
            self.printFinished(False)
            self.printStarted()
        if event == Events.PRINT_DONE:
            self.printFinished(True)
        if event == Events.DISCONNECTING:
            self.printFinished(False)
        if event == Events.DISCONNECTED:
            self.printFinished(False)
        if event == Events.PRINT_PAUSED:
            self.printPaused()
        if event == Events.PRINT_RESUMED:
            self.printResumed()
        if event == Events.PRINT_FAILED:
            self.printFinished(False)
        if event == Events.PRINT_CANCELLING:
            self.printFinished(False)
        if event == Events.PRINT_CANCELLED:
            self.printFinished(False)
        if event == Events.PRINTER_RESET:
            self.printFinished(False)

    def increaseBodyUploadSize(self, current_max_body_sizes, *args, **kwargs):
        return [("POST", '/createBlurMask', 50 * 1024 * 1024)]


__plugin_pythoncompat__ = ">=3.7,<4"
__plugin_name__ = "Timelapse+"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = TimelapsePlusPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.server.http.bodysize": __plugin_implementation__.increaseBodyUploadSize,
        "octoprint.comm.protocol.atcommand.sending": __plugin_implementation__.atCommand,
        "octoprint.comm.protocol.action": __plugin_implementation__.atAction
    }
