"""Image conditioning through Qwen hidden states, retaining the full loaded model."""
import torch


class ImageConditioningEncoder(torch.nn.Module):
    def __init__(self, encoder):
        super().__init__()
        self.encoder = encoder

    @property
    def config(self):
        return self.encoder.config

    @property
    def dtype(self):
        return next(self.encoder.parameters()).dtype

    @property
    def device(self):
        return next(self.encoder.parameters()).device

    def forward(self, *args, **kwargs):
        # Flux2Klein consumes only intermediate hidden_states. CausalLM's final
        # vocabulary projection cannot affect them and needlessly dequantizes
        # a large tied output matrix. Keep its weights loaded, skip its execution.
        return self.encoder.model(*args, **kwargs)
