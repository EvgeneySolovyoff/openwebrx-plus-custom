from csdr.chain.demodulator import BaseDemodulatorChain, FixedIfSampleRateChain, HdAudio, \
    FixedAudioRateChain, DeemphasisTauChain, MetaProvider, RdsChain
from pycsdr.modules import AmDemod, DcBlock, FmDemod, BCFmDemod, Limit, NfmDeemphasis, Agc, Afc, \
    WfmDeemphasis, FractionalDecimator, StereoFractionalDecimator, RealPart, Writer, Buffer
from pycsdr.types import Format, AgcProfile
from csdr.chain.toolbox import RdsDemodulator
from typing import Optional
import threading
import pickle
import math
import struct
import time
from owrx.feature import FeatureDetector


class Am(BaseDemodulatorChain):
    def __init__(self, agcProfile: AgcProfile = AgcProfile.SLOW):
        agc = Agc(Format.FLOAT)
        agc.setProfile(agcProfile)
        agc.setInitialGain(200)
        workers = [
            AmDemod(),
            DcBlock(),
            agc,
        ]
        super().__init__(workers)


class NFm(BaseDemodulatorChain):
    def __init__(self, sampleRate: int, agcProfile: AgcProfile = AgcProfile.SLOW):
        self.sampleRate = sampleRate
        agc = Agc(Format.FLOAT)
        agc.setProfile(agcProfile)
        workers = [
            FmDemod(),
            Limit(),
            NfmDeemphasis(sampleRate),
            agc,
        ]
        super().__init__(workers)

    def setSampleRate(self, sampleRate: int) -> None:
        if sampleRate == self.sampleRate:
            return
        self.sampleRate = sampleRate
        self.replace(2, NfmDeemphasis(sampleRate))


class WFm(BaseDemodulatorChain, FixedIfSampleRateChain, DeemphasisTauChain, HdAudio, MetaProvider, RdsChain):
    def __init__(self, sampleRate: int, tau: float, rdsRbds: bool):
        self.sampleRate = sampleRate
        self.tau = tau
        self.rdsRbds = rdsRbds
        self.limit = Limit()
        # this buffer is used to tap into the raw audio stream for redsea RDS decoding
        self.metaTapBuffer = Buffer(Format.FLOAT)

        # Temporary diagnostic FM stereo pilot detector.
        # Reads an independent copy of the 200 kHz MPX stream.
        self._pilotStereo = False
        self._pilotLastSent = None
        self._pilotReader = self.metaTapBuffer.getReader()
        self._pilotThread = threading.Thread(
            target=self._pilotMonitor,
            name="wfm-pilot-monitor",
            daemon=True
        )
        self._pilotThread.start()

        workers = [
            BCFmDemod(),
            self.limit,
            StereoFractionalDecimator(
                Format.FLOAT,
                200000,
                200000.0 / self.sampleRate,
                self.tau
            ),
        ]
        self.metaChain = None
        self.metaWriter = None
        super().__init__(workers)

    def _connect(self, w1, w2, buffer: Optional[Buffer] = None) -> None:
        if w1 is self.limit:
            buffer = self.metaTapBuffer
        super()._connect(w1, w2, buffer)

    @staticmethod
    def _pilotGoertzel(samples, frequency, sampleRate=200000.0):
        """Return normalized power at one MPX frequency."""
        n = len(samples)
        if n == 0:
            return 0.0

        omega = 2.0 * math.pi * frequency / sampleRate
        coeff = 2.0 * math.cos(omega)

        q0 = 0.0
        q1 = 0.0
        q2 = 0.0

        # Hann window reduces leakage from nearby MPX components.
        denom = max(n - 1, 1)

        for i, x in enumerate(samples):
            w = 0.5 - 0.5 * math.cos(
                2.0 * math.pi * i / denom
            )
            x *= w

            q0 = coeff * q1 - q2 + x
            q2 = q1
            q1 = q0

        power = q1 * q1 + q2 * q2 - coeff * q1 * q2

        return max(power / (n * n), 1e-20)

    def _pilotMonitor(self):
        reader = self._pilotReader
        pending = bytearray()

        # 50 ms at 200 kHz.
        # This gives good frequency discrimination around the 19 kHz pilot.
        blockSamples = 10000
        blockBytes = blockSamples * 4

        lastPrint = 0.0
        ratios = []

        while True:
            try:
                data = reader.read()

                if not data:
                    continue

                pending.extend(bytes(data))

                while len(pending) >= blockBytes:
                    raw = bytes(pending[:blockBytes])
                    del pending[:blockBytes]

                    samples = struct.unpack(
                        "<%df" % blockSamples,
                        raw
                    )

                    # Real FM stereo pilot is centred at 19 kHz.
                    # 18 and 20 kHz are used as neighbouring reference bins.
                    p18 = self._pilotGoertzel(samples, 18000.0)
                    p19 = self._pilotGoertzel(samples, 19000.0)
                    p20 = self._pilotGoertzel(samples, 20000.0)

                    neighbour = max((p18 + p20) * 0.5, 1e-20)

                    ratioDb = 10.0 * math.log10(
                        max(p19, 1e-20) / neighbour
                    )

                    pilotDb = 10.0 * math.log10(
                        max(p19, 1e-20)
                    )

                    neighbourDb = 10.0 * math.log10(neighbour)

                    ratios.append(ratioDb)

                    # Average roughly one second.
                    if len(ratios) > 20:
                        ratios.pop(0)

                    now = time.monotonic()

                    if now - lastPrint >= 0.25 and ratios:
                        avgRatio = sum(ratios) / len(ratios)

                        # True FM stereo pilot hysteresis:
                        # MONO -> STEREO at +15 dB
                        # STEREO -> MONO below +8 dB
                        oldState = self._pilotStereo

                        if not self._pilotStereo and avgRatio >= 15.0:
                            self._pilotStereo = True
                        elif self._pilotStereo and avgRatio <= 8.0:
                            self._pilotStereo = False

                        # Send only when state changes.
                        if self._pilotStereo != oldState:
                            print(
                                "[WFM STEREO STATE] ratio={:+.1f} dB => {}".format(
                                    avgRatio,
                                    "STEREO" if self._pilotStereo else "MONO"
                                ),
                                flush=True
                            )
                            self._sendPilotState()

                        lastPrint = now

            except Exception as e:
                print(
                    "[WFM PILOT] detector error: {}".format(e),
                    flush=True
                )
                time.sleep(1.0)

    def getFixedIfSampleRate(self):
        return 200000

    def setDeemphasisTau(self, tau: float) -> None:
        if tau == self.tau:
            return
        self.tau = tau
        self.replace(
            2,
            StereoFractionalDecimator(
                Format.FLOAT,
                200000,
                200000.0 / self.sampleRate,
                self.tau
            )
        )

    def setSampleRate(self, sampleRate: int) -> None:
        if sampleRate == self.sampleRate:
            return
        self.sampleRate = sampleRate
        self.replace(
            2,
            StereoFractionalDecimator(
                Format.FLOAT,
                200000,
                200000.0 / self.sampleRate,
                self.tau
            )
        )

    def _sendPilotState(self):
        writer = getattr(self, "metaWriter", None)

        if writer is None:
            return

        state = bool(getattr(self, "_pilotStereo", False))

        # Avoid duplicate metadata packets.
        if getattr(self, "_pilotLastSent", None) == state:
            return

        try:
            writer.write(pickle.dumps({
                "wfm_stereo": state
            }))
            self._pilotLastSent = state
        except Exception:
            pass

    def setMetaWriter(self, writer: Writer) -> None:
        if not FeatureDetector().is_available("rds"):
            return
        if self.metaChain is None:
            self.metaChain = RdsDemodulator(self.getFixedIfSampleRate(), self.rdsRbds)
            self.metaChain.setReader(self.metaTapBuffer.getReader())
        self.metaWriter = writer
        self.metaChain.setWriter(self.metaWriter)
        self._pilotLastSent = None
        self._sendPilotState()

    def stop(self):
        super().stop()
        if self.metaChain is not None:
            self.metaChain.stop()
            self.metaChain = None
            self.metaWriter = None

    def setRdsRbds(self, rdsRbds: bool) -> None:
        self.rdsRbds = rdsRbds
        if self.metaChain is not None:
            self.metaChain.stop()
            self.metaChain = RdsDemodulator(self.getFixedIfSampleRate(), self.rdsRbds)
            self.metaChain.setReader(self.metaTapBuffer.getReader())
            self.metaChain.setWriter(self.metaWriter)


class Ssb(BaseDemodulatorChain):
    def __init__(self, agcProfile: AgcProfile = AgcProfile.FAST):
        self.agc = Agc(Format.FLOAT)
        self.agc.setProfile(agcProfile)
        self.agc.setInitialGain(10)
        workers = [
            RealPart(),
            self.agc,
        ]
        super().__init__(workers)

    def setMaxGain(self, maxGain: float) -> None:
        self.agc.setMaxGain(maxGain)


class Empty(BaseDemodulatorChain):
    def __init__(self):
        super().__init__([])

    def getOutputFormat(self) -> Format:
        return Format.FLOAT

    def setWriter(self, writer):
        pass


class SAm(BaseDemodulatorChain):
    def __init__(self, sampleRate: int, agcProfile: AgcProfile = AgcProfile.SLOW):
        agc = Agc(Format.FLOAT)
        agc.setProfile(agcProfile)
        agc.setInitialGain(200)
        workers = [
            Afc(sampleRate),
            RealPart(),
            DcBlock(),
            agc,
        ]
        super().__init__(workers)


class SsbDigital(BaseDemodulatorChain, FixedAudioRateChain, HdAudio):
    def __init__(self, sampleRate: int = 48000):
        self.sampleRate = sampleRate
        workers = [
            RealPart(),
            Agc(Format.FLOAT),
        ]
        super().__init__(workers)

    def getFixedAudioRate(self) -> int:
        return self.sampleRate
