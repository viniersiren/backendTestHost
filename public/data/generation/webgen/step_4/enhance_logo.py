import cv2
import numpy as np
import os
import base64

# Set up paths
script_dir = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.dirname(script_dir)
input_path = os.path.join(data_dir, "raw_data", "step_1", "logo.png")

# Create assets directory path (ensure it matches frontend served path /assets/...)
# Compute repository root from data_dir (= public/data/generation/webgen)
repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(data_dir))))
public_assets_dir = os.path.join(repo_root, "public", "assets", "images", "hero")
assets_output_path = os.path.join(public_assets_dir, "logo.png")

# Output to same path and name as original logo.png (color variant)
output_path = input_path  # Color-enhanced output replaces original logo.png
gray_output_path = input_path.replace('.png', '_gray.png')  # Grayscale companion

# Create directories if they don't exist
os.makedirs(os.path.dirname(output_path), exist_ok=True)
os.makedirs(public_assets_dir, exist_ok=True)

# Load the image with unchanged flag to preserve transparency
image = cv2.imread(input_path, cv2.IMREAD_UNCHANGED)

# Ensure image is loaded correctly
if image is None:
    raise FileNotFoundError(f"Image at {input_path} not found")

print(f"Original image shape: {image.shape}")

# Handle different image formats (RGB, RGBA, Grayscale)
if len(image.shape) == 3 and image.shape[2] == 4:
    # RGBA image
    bgr = image[:, :, :3]
    original_alpha = image[:, :, 3]
    has_alpha = True
    print("Image has alpha channel")
elif len(image.shape) == 3 and image.shape[2] == 3:
    # RGB image
    bgr = image
    has_alpha = False
    print("Image is RGB")
else:
    # Grayscale image
    bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    has_alpha = False
    print("Image is grayscale")

# Convert to grayscale for analysis
gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

# ANALYZE THE IMAGE TO UNDERSTAND ITS CONTENT
print("Analyzing image content...")

if has_alpha:
    # Use existing alpha channel to identify silhouette
    # Areas with high alpha are the silhouette
    silhouette_from_alpha = original_alpha > 127
    alpha_coverage = np.sum(silhouette_from_alpha) / (image.shape[0] * image.shape[1])
    print(f"Alpha channel coverage: {alpha_coverage*100:.1f}%")
    
    if alpha_coverage > 0.01:  # If we have meaningful alpha content
        print("Using alpha channel to preserve silhouette")
        # Use the existing alpha but smooth the edges
        
        # Light denoising on the alpha channel
        clean_alpha = cv2.medianBlur(original_alpha, 3)
        
        # Smooth the edges with gentle Gaussian blur
        smooth_alpha = cv2.GaussianBlur(clean_alpha.astype(np.float32), (3, 3), 0.5)
        smooth_alpha = np.clip(smooth_alpha, 0, 255).astype(np.uint8)
        
        # Create pure black silhouette
        enhanced_bgr = np.zeros_like(bgr)
        enhanced_bgr[:, :] = [0, 0, 0]  # Pure black
        
        # Use the smoothed alpha
        final_alpha = smooth_alpha
        
        print("Enhanced using existing alpha channel")
    else:
        print("Alpha channel insufficient, analyzing grayscale content")
        has_alpha = False

if not has_alpha or alpha_coverage <= 0.01:
    # Analyze grayscale histogram to find good threshold
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
    
    # Find peaks in histogram (smooth 1D hist by reshaping to 2D for OpenCV)
    hist_2d = hist.reshape(-1, 1).astype(np.float32)
    hist_smooth_2d = cv2.GaussianBlur(hist_2d, (5, 1), 1.0)
    hist_smooth = hist_smooth_2d.flatten()
    
    # Statistics about the image
    mean_val = np.mean(gray)
    std_val = np.std(gray)
    
    print(f"Image statistics - Mean: {mean_val:.1f}, Std: {std_val:.1f}")
    
    # Find a good threshold using Otsu's method
    threshold_val, binary_otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    print(f"Otsu threshold: {threshold_val:.1f}")
    
    # Try a more conservative threshold
    # For silhouettes, we want to preserve dark areas
    conservative_threshold = min(threshold_val + 20, mean_val + std_val/2)
    print(f"Using conservative threshold: {conservative_threshold:.1f}")
    
    # Create silhouette mask - areas darker than threshold
    silhouette_mask = np.where(gray < conservative_threshold, 255, 0).astype(np.uint8)
    
    # Clean up with gentle morphological operations
    kernel = np.ones((3, 3), np.uint8)
    cleaned_mask = cv2.morphologyEx(silhouette_mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    cleaned_mask = cv2.morphologyEx(cleaned_mask, cv2.MORPH_OPEN, kernel, iterations=1)
    
    # Smooth the edges
    smoothed_mask = cv2.GaussianBlur(cleaned_mask.astype(np.float32), (3, 3), 0.5)
    smoothed_mask = np.clip(smoothed_mask, 0, 255).astype(np.uint8)
    
    # Create pure black silhouette
    enhanced_bgr = np.zeros_like(bgr)
    enhanced_bgr[:, :] = [0, 0, 0]  # Pure black
    
    # Use the smoothed mask as alpha
    final_alpha = smoothed_mask
    
    print("Enhanced using grayscale analysis")

# Final statistics
silhouette_pixels = np.sum(final_alpha > 50)
total_pixels = final_alpha.shape[0] * final_alpha.shape[1]
coverage_percent = 100 * silhouette_pixels / total_pixels

print(f"Final silhouette coverage: {silhouette_pixels}/{total_pixels} pixels ({coverage_percent:.1f}%)")

if coverage_percent < 1:
    print("WARNING: Very low silhouette coverage detected!")
    print("The image might be mostly background or the threshold needs adjustment.")
    
    # If coverage is too low, try a more aggressive approach
    if not has_alpha:
        print("Trying more aggressive threshold...")
        aggressive_threshold = mean_val
        aggressive_mask = np.where(gray < aggressive_threshold, 255, 0).astype(np.uint8)
        aggressive_coverage = np.sum(aggressive_mask > 50) / total_pixels
        print(f"Aggressive threshold {aggressive_threshold:.1f} gives {aggressive_coverage*100:.1f}% coverage")
        
        if aggressive_coverage > coverage_percent:
            final_alpha = aggressive_mask
            coverage_percent = aggressive_coverage * 100
            print(f"Using aggressive threshold - new coverage: {coverage_percent:.1f}%")

# Build two variants using the computed alpha mask:
# 1) Color-preserving inside silhouette
# 2) Grayscale inside silhouette

# Ensure we have a 3-channel BGR of original content
original_bgr = bgr.copy()

# Variant A: color-preserving
color_enhanced_rgba = cv2.merge([original_bgr[:, :, 0], original_bgr[:, :, 1], original_bgr[:, :, 2], final_alpha])

# Variant B: grayscale
gray_single = cv2.cvtColor(original_bgr, cv2.COLOR_BGR2GRAY)
gray_bgr = cv2.cvtColor(gray_single, cv2.COLOR_GRAY2BGR)
gray_enhanced_rgba = cv2.merge([gray_bgr[:, :, 0], gray_bgr[:, :, 1], gray_bgr[:, :, 2], final_alpha])

# MEMORY_ONLY: Return base64 instead of writing files when env flag is set
MEMORY_ONLY = os.environ.get('MEMORY_ONLY', '0') == '1'

if MEMORY_ONLY:
    # Emit two data streams: color then grayscale
    _, buf_color = cv2.imencode('.png', color_enhanced_rgba)
    b64_color = base64.b64encode(buf_color.tobytes()).decode('utf-8')
    print("ENHANCED_LOGO_COLOR_BASE64_START")
    print(b64_color)
    print("ENHANCED_LOGO_COLOR_BASE64_END")

    _, buf_gray = cv2.imencode('.png', gray_enhanced_rgba)
    b64_gray = base64.b64encode(buf_gray.tobytes()).decode('utf-8')
    print("ENHANCED_LOGO_GRAYSCALE_BASE64_START")
    print(b64_gray)
    print("ENHANCED_LOGO_GRAYSCALE_BASE64_END")
else:
    # Save exactly TWO images on disk:
    # 1) Color-enhanced to logo.png (replaces original)
    # 2) Grayscale companion to logo_gray.png
    cv2.imwrite(output_path, color_enhanced_rgba)
    cv2.imwrite(gray_output_path, gray_enhanced_rgba)
    print(f"Enhanced (color) logo saved to: {output_path}")
    print(f"Enhanced (grayscale) logo saved to: {gray_output_path}")

    # Clean up legacy files we no longer keep around to avoid having 3 files lingering
    # - Remove backup file if it exists
    legacy_backup = input_path.replace('.png', '_backup.png')
    if os.path.exists(legacy_backup):
        try:
            os.remove(legacy_backup)
            print(f"Removed legacy backup file: {legacy_backup}")
        except Exception as e:
            print(f"Warning: could not remove legacy backup file {legacy_backup}: {e}")

    # - Remove legacy assets copy if it exists (we no longer duplicate into assets here)
    if os.path.exists(assets_output_path):
        try:
            os.remove(assets_output_path)
            print(f"Removed legacy assets copy: {assets_output_path}")
        except Exception as e:
            print(f"Warning: could not remove legacy assets copy {assets_output_path}: {e}")
print("Adaptive logo enhancement complete!")
print("- Analyzed image content for optimal processing")
print("- Preserved silhouette shape")
print("- Applied edge smoothing for clean appearance")
print("- Created transparent background") 