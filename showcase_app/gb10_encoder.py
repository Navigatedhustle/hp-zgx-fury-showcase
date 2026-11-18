"""Image conditioning through Qwen hidden states, retaining the full loaded model."""
import torch


def restore_conditioning_ties(encoder):
    """FP8 Linear quantization unties the unused LM head from input embeddings.

    Restore the checkpoint's original sharing before materialization. FLUX uses
    only model hidden states, so its conditioning values remain unchanged.
    """
    if not getattr(encoder.config, 'tie_word_embeddings', False):
        return {'restored': False, 'duplicate_parameters_released': 0}
    embedding, projection = encoder.get_input_embeddings(), encoder.get_output_embeddings()
    if embedding is None or projection is None or embedding.weight.shape != projection.weight.shape:
        raise ValueError('Unexpected tied image encoder projection')
    duplicate = projection.weight is not embedding.weight
    count = projection.weight.numel() if duplicate else 0
    projection.weight = embedding.weight
    return {'restored': duplicate, 'duplicate_parameters_released': count}


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
