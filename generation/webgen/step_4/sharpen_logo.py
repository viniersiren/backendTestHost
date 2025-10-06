#!/usr/bin/env python3

import os
import cv2
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance
import logging
from pathlib import Path
import argparse

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LogoSharpener:
    """
    A class to sharpen silhouette design logos by enhancing edges and reducing noise.
    Specifically designed for logo images that need crisp, clean edges.
    """
    
    def __init__(self):
        self.supported_formats = ['.png', '.jpg', '.jpeg', '.bmp', '.tiff']
    
    def find_logo_files(self, search_dirs=None):
        """Find all logo.png files in the project directory."""
        if search_dirs is None:
            # Default search directories relative to this script
            script_dir = Path(__file__).parent
            project_root = script_dir.parent.parent.parent
            search_dirs = [
                project_root / "public" / "data" / "raw_data",
                project_root / "public" / "assets" / "images",
                project_root / "public" / "personal",
                script_dir.parent / "raw_data"  # step_4/../raw_data
            ]
        
        logo_files = []
        for search_dir in search_dirs:
            if search_dir.exists():
                # Find all logo files recursively
                for logo_file in search_dir.rglob("logo.*"):
                    if logo_file.suffix.lower() in self.supported_formats:
                        logo_files.append(logo_file)
                        logger.info(f"Found logo file: {logo_file}")
        
        return logo_files
    
    def preprocess_image(self, image_path):
        """Load and preprocess the image."""
        logger.info(f"Loading image: {image_path}")
        
        # Load with OpenCV for advanced processing
        cv_image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
        if cv_image is None:
            raise ValueError(f"Could not load image: {image_path}")
        
        # Load with PIL for some operations
        pil_image = Image.open(image_path)
        
        logger.info(f"Image loaded - Size: {pil_image.size}, Mode: {pil_image.mode}")
        
        return cv_image, pil_image
    
    def apply_noise_reduction(self, cv_image):
        """Apply noise reduction while preserving edges."""
        logger.info("Applying noise reduction...")
        
        # Convert to grayscale if needed for processing
        if len(cv_image.shape) == 3:
            gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
        else:
            gray = cv_image.copy()
        
        # Apply bilateral filter to reduce noise while preserving edges
        denoised = cv2.bilateralFilter(gray, 9, 75, 75)
        
        # If original was color, convert back
        if len(cv_image.shape) == 3:
            denoised = cv2.cvtColor(denoised, cv2.COLOR_GRAY2BGR)
        
        return denoised
    
    def enhance_edges_opencv(self, cv_image):
        """Enhance edges using OpenCV techniques."""
        logger.info("Enhancing edges with OpenCV...")
        
        # Convert to grayscale for edge detection
        if len(cv_image.shape) == 3:
            gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
        else:
            gray = cv_image.copy()
        
        # Apply Gaussian blur to reduce noise before edge detection
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        
        # Create sharpening kernel
        sharpening_kernel = np.array([
            [-1, -1, -1],
            [-1,  9, -1],
            [-1, -1, -1]
        ])
        
        # Apply sharpening filter
        sharpened = cv2.filter2D(blurred, -1, sharpening_kernel)
        
        # Enhance contrast for better edge definition
        enhanced = cv2.convertScaleAbs(sharpened, alpha=1.2, beta=10)
        
        # If original was color, convert back
        if len(cv_image.shape) == 3:
            enhanced = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
        
        return enhanced
    
    def enhance_edges_pil(self, pil_image):
        """Enhance edges using PIL techniques."""
        logger.info("Enhancing edges with PIL...")
        
        # Apply unsharp mask for edge enhancement
        sharpened = pil_image.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))
        
        # Apply edge enhancement filter
        edge_enhanced = sharpened.filter(ImageFilter.EDGE_ENHANCE_MORE)
        
        # Increase contrast
        enhancer = ImageEnhance.Contrast(edge_enhanced)
        contrast_enhanced = enhancer.enhance(1.2)
        
        # Increase sharpness
        sharpness_enhancer = ImageEnhance.Sharpness(contrast_enhanced)
        final_enhanced = sharpness_enhancer.enhance(1.5)
        
        return final_enhanced
    
    def apply_morphological_operations(self, cv_image):
        """Apply morphological operations to clean up the silhouette."""
        logger.info("Applying morphological operations...")
        
        # Convert to grayscale
        if len(cv_image.shape) == 3:
            gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
        else:
            gray = cv_image.copy()
        
        # Create morphological kernel
        kernel = np.ones((2, 2), np.uint8)
        
        # Apply closing to fill small gaps
        closed = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
        
        # Apply opening to remove small noise
        cleaned = cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel)
        
        # If original was color, convert back
        if len(cv_image.shape) == 3:
            cleaned = cv2.cvtColor(cleaned, cv2.COLOR_GRAY2BGR)
        
        return cleaned
    
    def sharpen_logo_comprehensive(self, image_path, output_path=None):
        """Apply comprehensive sharpening to a logo image."""
        logger.info(f"Starting comprehensive logo sharpening for: {image_path}")
        
        # Load images
        cv_image, pil_image = self.preprocess_image(image_path)
        
        # Method 1: OpenCV-based enhancement
        logger.info("Applying OpenCV-based enhancement...")
        denoised = self.apply_noise_reduction(cv_image)
        edges_enhanced_cv = self.enhance_edges_opencv(denoised)
        morphed = self.apply_morphological_operations(edges_enhanced_cv)
        
        # Convert back to PIL for final processing
        if len(morphed.shape) == 3:
            cv_enhanced_pil = Image.fromarray(cv2.cvtColor(morphed, cv2.COLOR_BGR2RGB))
        else:
            cv_enhanced_pil = Image.fromarray(morphed)
        
        # Method 2: PIL-based enhancement
        logger.info("Applying PIL-based enhancement...")
        pil_enhanced = self.enhance_edges_pil(pil_image)
        
        # Combine both methods by blending
        logger.info("Blending enhancement methods...")
        
        # Ensure both images are the same size and mode
        if cv_enhanced_pil.size != pil_enhanced.size:
            cv_enhanced_pil = cv_enhanced_pil.resize(pil_enhanced.size, Image.Resampling.LANCZOS)
        
        if cv_enhanced_pil.mode != pil_enhanced.mode:
            cv_enhanced_pil = cv_enhanced_pil.convert(pil_enhanced.mode)
        
        # Blend the two enhanced versions (70% PIL, 30% OpenCV)
        final_image = Image.blend(pil_enhanced, cv_enhanced_pil, 0.3)
        
        # Final sharpening pass
        final_sharpened = final_image.filter(ImageFilter.UnsharpMask(radius=0.5, percent=100, threshold=2))
        
        # Determine output path
        if output_path is None:
            input_path = Path(image_path)
            output_path = input_path.parent / f"{input_path.stem}_sharpened{input_path.suffix}"
        
        # Save the result
        final_sharpened.save(output_path, quality=95, optimize=True)
        logger.info(f"Sharpened logo saved to: {output_path}")
        
        return output_path
    
    def create_comparison_image(self, original_path, sharpened_path, comparison_path=None):
        """Create a side-by-side comparison image."""
        logger.info("Creating comparison image...")
        
        original = Image.open(original_path)
        sharpened = Image.open(sharpened_path)
        
        # Ensure both images are the same size
        max_height = max(original.height, sharpened.height)
        original = original.resize((int(original.width * max_height / original.height), max_height), Image.Resampling.LANCZOS)
        sharpened = sharpened.resize((int(sharpened.width * max_height / sharpened.height), max_height), Image.Resampling.LANCZOS)
        
        # Create comparison image
        total_width = original.width + sharpened.width + 20  # 20px gap
        comparison = Image.new('RGB', (total_width, max_height), 'white')
        
        # Paste images
        comparison.paste(original, (0, 0))
        comparison.paste(sharpened, (original.width + 20, 0))
        
        # Determine output path
        if comparison_path is None:
            input_path = Path(original_path)
            comparison_path = input_path.parent / f"{input_path.stem}_comparison.png"
        
        comparison.save(comparison_path)
        logger.info(f"Comparison image saved to: {comparison_path}")
        
        return comparison_path

def main():
    """Main function to run the logo sharpening script."""
    parser = argparse.ArgumentParser(description='Sharpen silhouette design logos')
    parser.add_argument('--input', '-i', type=str, help='Specific logo file to process')
    parser.add_argument('--output', '-o', type=str, help='Output file path')
    parser.add_argument('--all', '-a', action='store_true', help='Process all logo files found in the project')
    parser.add_argument('--comparison', '-c', action='store_true', help='Create before/after comparison images')
    
    args = parser.parse_args()
    
    sharpener = LogoSharpener()
    
    if args.input:
        # Process specific file
        input_path = Path(args.input)
        if not input_path.exists():
            logger.error(f"Input file not found: {input_path}")
            return
        
        try:
            output_path = sharpener.sharpen_logo_comprehensive(input_path, args.output)
            
            if args.comparison:
                sharpener.create_comparison_image(input_path, output_path)
                
            logger.info("Logo sharpening completed successfully!")
            
        except Exception as e:
            logger.error(f"Error processing logo: {e}")
            
    elif args.all:
        # Process all logo files
        logo_files = sharpener.find_logo_files()
        
        if not logo_files:
            logger.warning("No logo files found in the project")
            return
        
        for logo_file in logo_files:
            try:
                logger.info(f"Processing: {logo_file}")
                output_path = sharpener.sharpen_logo_comprehensive(logo_file)
                
                if args.comparison:
                    sharpener.create_comparison_image(logo_file, output_path)
                    
            except Exception as e:
                logger.error(f"Error processing {logo_file}: {e}")
                continue
        
        logger.info(f"Processed {len(logo_files)} logo files")
        
    else:
        # Default: look for logo.png in common locations and process them
        script_dir = Path(__file__).parent
        common_logo_paths = [
            script_dir.parent / "raw_data" / "logo.png",
            script_dir.parent / "raw_data" / "step_1" / "logo.png",
            script_dir.parent.parent.parent / "public" / "assets" / "images" / "logo.png"
        ]
        
        processed = False
        for logo_path in common_logo_paths:
            if logo_path.exists():
                try:
                    logger.info(f"Found and processing: {logo_path}")
                    output_path = sharpener.sharpen_logo_comprehensive(logo_path)
                    
                    if args.comparison:
                        sharpener.create_comparison_image(logo_path, output_path)
                    
                    processed = True
                    
                except Exception as e:
                    logger.error(f"Error processing {logo_path}: {e}")
                    continue
        
        if not processed:
            logger.warning("No logo files found. Use --input to specify a file or --all to find all logos")
            logger.info("Usage examples:")
            logger.info("  python sharpen_logo.py --input /path/to/logo.png")
            logger.info("  python sharpen_logo.py --all --comparison")

if __name__ == "__main__":
    main() 