# p3audiofile
import opuslib
import struct
import numpy as np
import sounddevice as sd
import argparse

def play_p3_file(input_file):
    """
    p3audiofile
    p3: [1type, 1, 2, Opusdata]
    """
    # initializeOpus
    sample_rate = 16000  # 16000Hz
    channels = 1  # 
    decoder = opuslib.Decoder(sample_rate, channels)
    
    #  (60ms)
    frame_size = int(sample_rate * 60 / 1000)
    
    # audio
    stream = sd.OutputStream(
        samplerate=sample_rate,
        channels=channels,
        dtype='int16'
    )
    stream.start()
    
    try:
        with open(input_file, 'rb') as f:
            print(f": {input_file}")
            
            while True:
                #  (4)
                header = f.read(4)
                if not header or len(header) < 4:
                    break
                
                packet_type, reserved, data_len = struct.unpack('>BBH', header)
                
                # Opusdata
                opus_data = f.read(data_len)
                if not opus_data or len(opus_data) < data_len:
                    break
                
                # Opusdata
                pcm_data = decoder.decode(opus_data, frame_size)
                
                # numpy
                audio_array = np.frombuffer(pcm_data, dtype=np.int16)
                
                # audio
                stream.write(audio_array)
                
    except KeyboardInterrupt:
        print("\nstop")
    finally:
        stream.stop()
        stream.close()
        print("")

def main():
    parser = argparse.ArgumentParser(description='p3audiofile')
    parser.add_argument('input_file', help='p3file')
    args = parser.parse_args()
    
    play_p3_file(args.input_file)

if __name__ == "__main__":
    main() 
