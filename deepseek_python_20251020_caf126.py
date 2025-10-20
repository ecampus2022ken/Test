import os
import subprocess
import sys
import time
import threading
from pathlib import Path
import re

class FixedProgressConverter:
    def __init__(self):
        self.current_process = None
        self.is_converting = False
        
    def get_file_size(self, file_path):
        """Dapatkan ukuran file dalam bytes"""
        try:
            return os.path.getsize(file_path)
        except:
            return 0
    
    def get_video_duration(self, input_file):
        """Dapatkan durasi video menggunakan FFprobe - METHOD 1"""
        try:
            cmd = [
                'ffprobe', '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(input_file)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            duration = float(result.stdout.strip())
            print(f"⏱️  Video duration: {duration:.2f} seconds")
            return duration
        except Exception as e:
            print(f"⚠️  Cannot get duration via method 1: {e}")
            return self.get_video_duration_method2(input_file)
    
    def get_video_duration_method2(self, input_file):
        """Dapatkan durasi video - METHOD 2 (fallback)"""
        try:
            cmd = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'csv=p=0',
                str(input_file)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            duration = float(result.stdout.strip())
            print(f"⏱️  Video duration (method 2): {duration:.2f} seconds")
            return duration
        except Exception as e:
            print(f"⚠️  Cannot get duration via method 2: {e}")
            return 0
    
    def monitor_progress_file_size(self, input_file, output_file, duration):
        """Monitor progress berdasarkan ukuran file output vs input"""
        input_size = self.get_file_size(input_file)
        start_time = time.time()
        last_size = 0
        
        print("📊 Starting file-based progress monitoring...")
        
        while self.is_converting:
            try:
                if os.path.exists(output_file):
                    current_size = self.get_file_size(output_file)
                    
                    if input_size > 0 and current_size > 0:
                        # Estimate progress based on file size ratio
                        progress = min(100, (current_size / input_size) * 100)
                        
                        # Calculate speed
                        elapsed_time = time.time() - start_time
                        if elapsed_time > 0 and current_size > last_size:
                            speed_mbps = (current_size - last_size) / (1024 * 1024) / 2  # MB per 2 seconds
                            last_size = current_size
                        else:
                            speed_mbps = 0
                        
                        # Estimate remaining time
                        if progress > 1 and speed_mbps > 0:
                            remaining_size = input_size - current_size
                            remaining_time = remaining_size / (speed_mbps * 1024 * 1024) if speed_mbps > 0 else 0
                        else:
                            remaining_time = 0
                        
                        # Format time
                        elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed_time))
                        remaining_str = time.strftime("%H:%M:%S", time.gmtime(remaining_time))
                        
                        print(f"📈 Progress: {progress:6.2f}% | "
                              f"Elapsed: {elapsed_str} | "
                              f"ETA: {remaining_str} | "
                              f"Speed: {speed_mbps:5.1f} MB/s | "
                              f"Size: {current_size/(1024**3):6.2f} GB", 
                              end='\r')
                
                time.sleep(2)  # Update every 2 seconds
                
            except Exception as e:
                print(f"\n⚠️  Progress monitoring error: {e}")
                break
        
        print()  # New line after progress
    
    def parse_ffmpeg_time(self, time_str):
        """Parse time string dari FFmpeg (hh:mm:ss.ms) ke seconds"""
        try:
            if '.' in time_str:
                time_part, ms_part = time_str.split('.')
                ms = float('0.' + ms_part)
            else:
                time_part = time_str
                ms = 0
            
            parts = time_part.split(':')
            if len(parts) == 3:  # hh:mm:ss
                hours, minutes, seconds = map(int, parts)
                return hours * 3600 + minutes * 60 + seconds + ms
            elif len(parts) == 2:  # mm:ss
                minutes, seconds = map(int, parts)
                return minutes * 60 + seconds + ms
            else:  # ss
                return float(time_str)
        except:
            return 0
    
    def monitor_ffmpeg_output(self, process, duration, start_time):
        """Monitor FFmpeg output untuk progress real-time"""
        print("🔍 Monitoring FFmpeg output...")
        
        while self.is_converting:
            try:
                # Read line dari stderr (FFmpeg outputs progress to stderr)
                line = process.stderr.readline()
                if not line and process.poll() is not None:
                    break
                
                if line:
                    # Debug: print FFmpeg output (bisa di-comment jika terlalu verbose)
                    # print(f"FFmpeg: {line.strip()}")
                    
                    # Cari time information dalam output
                    if 'time=' in line:
                        time_match = re.search(r'time=(\d+:\d+:\d+\.\d+)', line)
                        if time_match:
                            current_time_str = time_match.group(1)
                            current_seconds = self.parse_ffmpeg_time(current_time_str)
                            
                            if duration > 0:
                                progress_percent = (current_seconds / duration) * 100
                                elapsed_time = time.time() - start_time
                                
                                # Calculate ETA
                                if progress_percent > 0:
                                    total_estimated_time = elapsed_time / (progress_percent / 100)
                                    remaining_time = total_estimated_time - elapsed_time
                                    
                                    elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed_time))
                                    remaining_str = time.strftime("%H:%M:%S", time.gmtime(remaining_time))
                                    
                                    print(f"⏳ FFmpeg Progress: {progress_percent:6.2f}% | "
                                          f"Time: {current_time_str} | "
                                          f"Elapsed: {elapsed_str} | "
                                          f"ETA: {remaining_str}", 
                                          end='\r')
                
            except Exception as e:
                print(f"\n⚠️  FFmpeg monitoring error: {e}")
                break
    
    def convert_single_file(self, input_file, output_file, crf=20, preset='medium'):
        """Convert single file dengan progress monitoring yang bekerja"""
        
        file_size_gb = self.get_file_size(input_file) / (1024**3)
        duration = self.get_video_duration(input_file)
        
        print(f"\n🎬 Converting: {input_file.name}")
        print(f"📊 File Size: {file_size_gb:.2f} GB")
        print(f"⏱️  Duration: {duration:.2f} seconds")
        print(f"⚙️  Settings: CRF={crf}, Preset={preset}")
        print("-" * 60)
        
        # Skip jika output sudah ada
        if output_file.exists():
            print(f"⏭️  Output exists, skipping: {output_file.name}")
            return True
        
        cmd = [
            'ffmpeg',
            '-i', str(input_file),
            '-c:v', 'libx264',
            '-crf', str(crf),
            '-preset', preset,
            '-c:a', 'aac',
            '-b:a', '192k',
            '-movflags', '+faststart',
            '-y',  # Overwrite output
            '-progress', 'pipe:1',  # Enable progress reporting
            '-loglevel', 'info',    # More verbose logging
            str(output_file)
        ]
        
        self.is_converting = True
        start_time = time.time()
        
        try:
            # Start FFmpeg process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1,
                text=True
            )
            
            self.current_process = process
            
            # Start progress monitoring threads
            progress_thread1 = threading.Thread(
                target=self.monitor_progress_file_size,
                args=(input_file, output_file, duration),
                daemon=True
            )
            progress_thread1.start()
            
            progress_thread2 = threading.Thread(
                target=self.monitor_ffmpeg_output,
                args=(process, duration, start_time),
                daemon=True
            )
            progress_thread2.start()
            
            # Wait for process to complete
            process.wait()
            self.is_converting = False
            
            end_time = time.time()
            conversion_time = end_time - start_time
            
            if process.returncode == 0:
                output_size_gb = self.get_file_size(output_file) / (1024**3)
                compression_ratio = file_size_gb / output_size_gb if output_size_gb > 0 else 0
                
                print(f"\n✅ Conversion successful!")
                print(f"📦 Output: {output_file.name}")
                print(f"⏱️  Total Time: {conversion_time:.1f} seconds ({conversion_time/60:.1f} minutes)")
                print(f"📊 Output Size: {output_size_gb:.2f} GB")
                print(f"🎯 Compression Ratio: {compression_ratio:.1f}x")
                return True
            else:
                print(f"\n❌ Conversion failed with code: {process.returncode}")
                # Print error output
                stderr_output = process.stderr.read()
                if stderr_output:
                    print(f"Error details: {stderr_output[-500:]}")  # Last 500 chars
                return False
                
        except Exception as e:
            print(f"\n❌ Error during conversion: {e}")
            self.is_converting = False
            return False
        finally:
            self.current_process = None
    
    def convert_all_files(self, input_folder="input", output_folder="output"):
        """Convert semua file dalam folder"""
        input_path = Path(input_folder)
        output_path = Path(output_folder)
        
        # Buat folder jika belum ada
        input_path.mkdir(exist_ok=True)
        output_path.mkdir(exist_ok=True)
        
        # Cari file video
        video_extensions = ['.mxf', '.mov', '.mp4', '.avi', '.mkv', '.mts', '.m2ts']
        video_files = []
        
        for ext in video_extensions:
            video_files.extend(input_path.rglob(f"*{ext}"))
        
        if not video_files:
            print("❌ Tidak ada file video yang ditemukan di folder 'input'")
            print("💡 Supported formats: MXF, MOV, MP4, AVI, MKV, MTS, M2TS")
            return
        
        # Urutkan berdasarkan ukuran
        video_files.sort(key=lambda x: self.get_file_size(x), reverse=True)
        
        total_size_gb = sum(self.get_file_size(f) for f in video_files) / (1024**3)
        print(f"🎬 Found {len(video_files)} files, Total: {total_size_gb:.2f} GB")
        
        successful = 0
        failed = 0
        
        for video_file in video_files:
            file_size_gb = self.get_file_size(video_file) / (1024**3)
            print(f"\n{'='*70}")
            print(f"🎥 Processing: {video_file.name}")
            print(f"💾 Size: {file_size_gb:.2f} GB")
            print(f"{'='*70}")
            
            relative_path = video_file.relative_to(input_path)
            output_file = output_path / relative_path.with_suffix('.mp4')
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            if self.convert_single_file(video_file, output_file):
                successful += 1
            else:
                failed += 1
            
            print()  # New line between files
        
        print(f"\n{'='*50}")
        print(f"📊 CONVERSION SUMMARY:")
        print(f"✅ Successful: {successful}")
        print(f"❌ Failed: {failed}")
        print(f"{'='*50}")

def main():
    print("🎬 MXF to MP4 Converter - Fixed Progress Monitoring")
    print("=" * 60)
    print("🔧 Features:")
    print("   • Real-time progress monitoring")
    print("   • File size based progress")
    print("   • FFmpeg output parsing")
    print("   • ETA and speed calculation")
    print("=" * 60)
    
    # Check input folder
    input_path = Path("input")
    if not input_path.exists():
        input_path.mkdir(exist_ok=True)
        print("📁 Created 'input' folder")
        print("💡 Place your video files in the 'input' folder")
        return
    
    # Check if input folder has files
    video_files = list(input_path.rglob("*.*"))
    if not video_files:
        print("❌ No files found in 'input' folder")
        print("💡 Place your video files in the 'input' folder")
        return
    
    converter = FixedProgressConverter()
    converter.convert_all_files()

if __name__ == "__main__":
    main()