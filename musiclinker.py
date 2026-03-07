class MusicLinker:
    def __init__(self):
        self.enabled = True  # Toggle setting to enable or disable music
        self.allowed_channels = []  # List of channels where music can be used
        self.allow_dm = False  # Setting to enable DM feature
        self.last_song = None  # Track last played song

    def toggle_music(self, status: bool):
        """Enable or disable music functionality."""
        self.enabled = status

    def set_channel_restrictions(self, channels: list):
        """Restrict music functionality to specific channels."""
        self.allowed_channels = channels

    def enable_dm_feature(self):
        """Allow music-related messages in Direct Messages."""
        self.allow_dm = True

    def track_last_song(self, song: str):
        """Track the last song played."""
        self.last_song = song

    def dismiss_last_song(self):
        """Dismiss the last song information."""
        self.last_song = None

    # Other music functionalities...