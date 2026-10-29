from providers.builtin.ytdlp_adapter import YtDlpAdapter
class ProviderRegistry:
    def __init__(self): self.builtin = YtDlpAdapter()
    def get_provider_for_platform(self, plat: str): return self.builtin
provider_registry = ProviderRegistry()