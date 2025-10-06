import cv2
import numpy as np
import os
import sys

"""
Usage:
  python clipimage.py /absolute/or/relative/path/to/image.png [--copy-to-assets clipped_name.png]

Behavior:
  - Overwrites the input image in-place with a clipped (transparent background, grayscale base) version.
  - Optionally also writes a copy under project assets/images/hero with the provided filename.
"""

# Resolve paths
script_dir = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.dirname(script_dir)
# Compute project root (four levels up from data_dir: webgen -> generation -> data -> public -> project root)
project_root = os.path.dirname(
    os.path.dirname(
        os.path.dirname(
            os.path.dirname(data_dir)
        )
    )
)

if len(sys.argv) < 2:
    # Default fallback to legacy path if no arg supplied
    input_path = os.path.join(data_dir, "raw_data", "step_1", "logo.png")
else:
    input_path = sys.argv[1]

# Optional copy to assets
copy_to_assets = None
if len(sys.argv) >= 4 and sys.argv[2] == '--copy-to-assets':
    copy_to_assets = sys.argv[3]

assets_dir = os.path.join(project_root, "public", "assets", "images", "hero")
os.makedirs(assets_dir, exist_ok=True)

# Load the image with unchanged flag to preserve transparency
image = cv2.imread(input_path, cv2.IMREAD_UNCHANGED)

# Ensure image is loaded correctly
if image is None:
    raise FileNotFoundError(f"Image at {input_path} not found")

# Convert to grayscale to remove saturation (desaturate the image)
gray = cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2GRAY)

# Apply thresholding to create a mask to remove the background
_, binary_mask = cv2.threshold(gray, 50, 255, cv2.THRESH_BINARY_INV)

# Create an alpha channel based on the binary mask
alpha_channel = np.where(binary_mask == 255, 255, 0).astype(np.uint8)

# Convert grayscale to a 3-channel image
gray_3channel = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

# Merge grayscale image with new alpha channel
output_image = cv2.merge((gray_3channel, alpha_channel))

# Overwrite the input image in-place
cv2.imwrite(input_path, output_image)

# Optional additional copies for compatibility
legacy_output_dir = os.path.join(data_dir, "raw_data", "step_3")
os.makedirs(legacy_output_dir, exist_ok=True)
legacy_output_path = os.path.join(legacy_output_dir, "clipped.png")
cv2.imwrite(legacy_output_path, output_image)

if copy_to_assets:
    assets_output_path = os.path.join(assets_dir, copy_to_assets)
    cv2.imwrite(assets_output_path, output_image)
    print(f"Also copied to {assets_output_path} for website assets")

print(f"Overwrote input with clipped image: {input_path}")
print(f"Compatibility copy saved as {legacy_output_path}")
