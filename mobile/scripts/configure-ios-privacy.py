"""Apply privacy descriptions after Codemagic regenerates the iOS project."""
from pathlib import Path
import plistlib

path = Path(__file__).resolve().parents[1] / 'ios' / 'App' / 'App' / 'Info.plist'
with path.open('rb') as source:
    settings = plistlib.load(source)
settings.update({
    'NSCameraUsageDescription': 'Take an identity photo for review, only when you choose to capture it.',
    'NSPhotoLibraryUsageDescription': 'Choose a photo for your DhaShu profile.',
    'NSPhotoLibraryAddUsageDescription': 'Photo saving is not used for identity captures.',
})
with path.open('wb') as target:
    plistlib.dump(settings, target)
print('Applied iOS camera and photo privacy descriptions.')
