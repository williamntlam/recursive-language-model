"""Tiny autocast-style fixture for repo Q&A tests."""

def autocast_cpu_bf16(x):
    """AUTOCAST_CPU_BF16_IMPL_MARKER: fake CPU bfloat16 autocast path."""
    return x
