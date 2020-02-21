import numpy as np

from tacotron2.hparams import create_hparams
from tacotron2.train import load_model
from tacotron2.waveglow.denoiser import Denoiser
from tacotron2.text import text_to_sequence

from tacotron2.waveglow.glow import WaveGlow

from data_utils import *


class TTS:
    """
    A Text to Speech Generator, a mel spectogram generator (tacotron) with a speech generator (waveglow)
    """
    def __init__(self, tacotron_weights_path, waveglow_cfg_path, waveglow_weights_path, sampling_rate=22050):
        """
        args:
            tacotron_weights_path: path to the tacotron weights
            waveglow_weights_path: path to the waveglow weights
            sampling_rate: the rate that audio representations are sampled per second
        """
        hparams = create_hparams()
        hparams.sampling_rate = sampling_rate

        self.tacotron = load_model(hparams)
        self.tacotron.load_state_dict(torch.load(tacotron_weights_path)['state_dict'])
        self.tacotron.cuda().eval().half()

        with open(waveglow_cfg_path, "r", encoding='utf-8') as reader:
            text = reader.read()
        wg_cfg = json.loads(text)['waveglow_config']
        self.waveglow = WaveGlow(wg_cfg['n_mel_channels'], wg_cfg['n_flows'], wg_cfg['n_group'],
                                 wg_cfg['n_early_every'], wg_cfg['n_early_size'], wg_cfg['WN_config'])

        self.waveglow.load_state_dict(torch.load(waveglow_weights_path))
        self.waveglow.cuda().eval().half()

        for k in self.waveglow.convinv:
            k.float()

        self.denoiser = Denoiser(self.waveglow)

    def __call__(self, text, visualize=False, denoise=True):
        """
        inference only for now
        args:
            text: The text to convert
            visualize: Whether to display intermediary results, the mel spectograms
            denoise: whether to reduce the waveglow bias to denoise the audio
        """

        with torch.no_grad():
            sequence = np.array(text_to_sequence(text, ['english_cleaners']))[None, :]
            sequence = torch.autograd.Variable(torch.from_numpy(sequence)).cuda().long()

            mel_outputs, mel_outputs_postnet, _, alignments = self.tacotron.inference(sequence)

            if visualize:
                plot_data((mel_outputs.float().data.cpu().numpy()[0],
                           mel_outputs_postnet.float().data.cpu().numpy()[0],
                           alignments.float().data.cpu().numpy()[0].T))

            audio = self.waveglow.infer(mel_outputs_postnet, sigma=0.666)

            if denoise:
                audio = self.denoiser(audio, strength=0.01)[:, 0]

            return audio