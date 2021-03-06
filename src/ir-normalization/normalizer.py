"""Functions for transforming 16-bit thermal images into 8-bits"""
# Imports
import argparse
import datetime
from functools import partial
from multiprocessing import Pool, Manager, Value, cpu_count
import os
import sys
import time

import numpy as np
from PIL import Image
import png


# Functions
def lin_normalize_image(image_array, bit_8, bottom=None, top=None):
    """Linear normalization for an image array
    Inputs:
        image_array: np.ndarray, image data to be normalized
        bit_8: boolean, if true outputs 8 bit, otherwise outputs 16 bit
        bottom: float, value to map to 0 in the new array
        top: float, value to map to 2^(bit_depth)-1 in the new array
    Output:
        scaled_image: nd.ndarray, scaled image between 0 and 2^(bit_depth) - 1
    """
    if bottom is None:
        bottom = np.min(image_array)
    if top is None:
        top = np.max(image_array)

    scaled_image = (image_array - bottom) / (top - bottom)
    scaled_image[scaled_image < 0] = 0
    scaled_image[scaled_image > 1] = 1
    
    if bit_8:
        scaled_image = np.floor(scaled_image * 255).astype(np.uint8)  # Map to [0, 2^8 - 1]
    else:
        scaled_image = np.floor(scaled_image * 65535).astype(np.uint16)  # Map to [0, 2^16 - 1]

    return scaled_image

def parse_arguments(sys_args):
    """Parses the input and output directories from the arguments
    Input:
        sys_args: list, the arguments to be parsed
    Output:
        input_directory: string, path to the input image directory
        output_directory: string, path to the output image directory
        bit_8: boolean, set to true to output 8-bit images, or false for 16-bit
    """
    # Set up parse
    parser = argparse.ArgumentParser(
        description='Command line interface for thermal image normalization')
    parser.add_argument('--indir', type=str,
                        required=True, help='relative path to directory containing images')
    parser.add_argument('--outdir', type=str,
                        default=None, help='relative path to the output directory')
    parser.add_argument('--bit8', action='store_true',
                        default=False, help='include to output 8-bit images')
    # Parse
    args = parser.parse_args(sys_args)

    # Store values
    input_directory = args.indir

    if args.outdir is None:
        output_directory = input_directory
    else:
        output_directory = args.outdir

    bit_8 = args.bit8

    return input_directory, output_directory, bit_8


def curate_files(input_directory, output_directory, bit_8):
    """Generates name lists for input and output images
    Inputs:
        input_directory: string, path to the input image directory
        output_directory: string, path to the output image directory
        bit_8: boolean, if true outputs 8 bit, otherwise outputs 16 bit
    Output:
        input_files: list, contains the file names of the incoming images
        output_files: list, contains the file names of the outgoing images
    """
    all_files = os.listdir(input_directory)

    input_files = [x for x in all_files if x.find('16BIT.PNG') != -1]
    if bit_8:
        output_files = [x.replace('16BIT', '8BIT-N') for x in input_files]
    else:
        output_files = [x.replace('16BIT.', '16BIT-N.') for x in input_files]

    input_files = [os.path.join(input_directory, x) for x in input_files]
    output_files = [os.path.join(output_directory, x) for x in output_files]

    return input_files, output_files


def parse_filename(filename):
    """Gets the camera position argument from filename
    Input:
        filename: string, name of the image file
    Output:
        camera_pos: string, capital letter position of the camera
    """
    tokens = os.path.basename(filename).split('_')
 
    for token in tokens:
      if token == 'P' or token == 'C' or token == 'S':
        camera_pos = token
        break
    else:
      print('Warning: Bad filename format %s' % filename)

    return camera_pos
 

def get_scaling_values(filename, num_rows):
    """Returns the bottom and top scaling parameters based on filename
    Inputs:
        filename: string, name of the file
        num_rows: int, number of rows in the image
    Outputs:
        bottom: int, number that maps to 0 in scaled image
        top: int, number that maps to 255 in scaled image
    """
    camera_pos = parse_filename(filename) 
    
    # camera_pos S and default
    bottom = 51000
    top = 57500

    if camera_pos == "P":
        if num_rows == 512:
            bottom = 53500
            top = 56500
        elif num_rows == 480:
            bottom = 50500
            top = 58500
        else:
            print('Unknown camera size for file %s' % filename)
    elif camera_pos == "C":
        bottom = 50500
        top = 58500

    return bottom, top



def process_file(len_inputs, bit_8, prev_time, prev_time_lock, in_file, output_file, index):
    """Reads an image, processes it, and outputs the result. Runs in a thread.

    Returns True on success, False otherwise.
    """
    if index % 1000 == 0:
        cur_time = time.time()
        time_diff = cur_time - prev_time.value
        time_est_sec = time_diff * (len_inputs - index) / 1000
        time_est = datetime.timedelta(seconds=time_est_sec)
        print('%d of %d -- %.2f sec. Time remaining: %s' % 
	    (index, len_inputs, time_diff, time_est))
        with prev_time_lock:
            prev_time.value = cur_time

    try:
        cur_data = np.array(Image.open(in_file))
        bottom, top = get_scaling_values(in_file, cur_data.shape[0])
        normalized = lin_normalize_image(cur_data, bit_8, bottom, top)
    
        if bit_8:
    	    save_im = Image.fromarray(normalized)
    	    save_im.save(output_file)
        else:
       	    # Pillow does not support 16-bit grayscale pngs
       	    # So switched to pypng
       	    with open(output_file, 'wb') as f:
       	        writer = png.Writer(width=normalized.shape[1], 
       	    			height=normalized.shape[0], 
       	    			bitdepth=16, 
       	    			greyscale=True)
       	        normalized_list = normalized.tolist()
       	        writer.write(f, normalized_list)
        return True
    except Exception as e:
        print(e)
        print('Unable to load {}'.format(in_file))
        return False
    

def main(sys_args):
    """Function that is called by the command line"""
    # Parses the arguments
    input_directory, output_directory, bit_8 = parse_arguments(sys_args[1:])
    print('Input directory: %s' % input_directory)
    print('Output directory: %s' % output_directory)
    print('bit_8: %s' % bit_8)

    input_files, output_files = curate_files(input_directory, output_directory, bit_8)
    print('Found {} files for processing'.format(len(input_files)))


    m = Manager()
    prev_time = m.Value('d', time.time())
    prev_time_lock = m.Lock()
    process_file_partial = partial(process_file, len(input_files), bit_8, prev_time, prev_time_lock)

    # Process using multiple cores.
    num_workers = cpu_count() - 1 or 1    
    with Pool(num_workers) as pool:
        results = pool.starmap(process_file_partial, 
                               [(in_file, output_files[index], index) 
                                for index, in_file in enumerate(input_files)], 
                               chunksize=1)
    print('Done!')
    print('Completed converting {} files'.format(sum(1 for x in results if x)))


if __name__ == "__main__":
    main(sys.argv)

