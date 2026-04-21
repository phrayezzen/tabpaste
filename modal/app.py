"""
TabPaste Modal Backend

Pipeline: YouTube URL → Audio → MIDI → Viterbi String Assignment → MusicXML
"""

import os
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

import modal

# Modal app definition
app = modal.App("tabpaste")

# Image with all dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "basic-pitch>=0.3.0",
        "pytubefix",
        "supabase>=2.0.0",
        "numpy",
        "fastapi[standard]",
    )
)

# Supabase credentials secret
supabase_secret = modal.Secret.from_name("supabase-credentials")


@dataclass
class TabNote:
    """A note with string and fret assignment for guitar tablature."""
    start: float      # Start time in seconds
    duration: float   # Duration in seconds
    midi_pitch: int   # MIDI pitch number
    string: int       # Guitar string (1-6, 1=high E)
    fret: int         # Fret number (0=open, up to 15)


# Standard guitar tuning (MIDI pitch for each open string)
# String 1 = high E (E4), String 6 = low E (E2)
STANDARD_TUNING = {
    1: 64,  # E4
    2: 59,  # B3
    3: 55,  # G3
    4: 50,  # D3
    5: 45,  # A2
    6: 40,  # E2
}
MAX_FRET = 15
CHORD_TIME_THRESHOLD = 0.05  # 50ms - notes within this are a chord


def get_supabase_client():
    """Create Supabase client from environment variables."""
    from supabase import create_client
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)


def update_job_status(job_id: str, status: str, detail: Optional[str] = None, error: Optional[str] = None, musicxml_path: Optional[str] = None):
    """Update job status in Supabase."""
    client = get_supabase_client()
    update_data = {"status": status}
    if detail:
        update_data["status_detail"] = detail
    if error:
        update_data["error"] = error
    if musicxml_path:
        update_data["musicxml_path"] = musicxml_path
    client.table("jobs").update(update_data).eq("id", job_id).execute()


def download_audio(youtube_url: str, tmpdir: str) -> tuple[str, str]:
    """
    Download audio from YouTube URL using pytubefix.

    Returns: (audio_path, video_title)
    """
    import subprocess
    from pytubefix import YouTube

    # Download audio stream
    yt = YouTube(youtube_url)
    title = yt.title or "Untitled"

    # Get best audio stream
    audio_stream = yt.streams.filter(only_audio=True).order_by("abr").desc().first()
    if not audio_stream:
        raise ValueError("No audio stream available for this video")

    # Download to temp directory
    downloaded_file = audio_stream.download(output_path=tmpdir, filename="audio_raw")

    # Convert to WAV with correct sample rate using ffmpeg
    audio_path = os.path.join(tmpdir, "audio.wav")
    subprocess.run([
        "ffmpeg", "-y", "-i", downloaded_file,
        "-ar", "22050",  # 22050 Hz sample rate (basic-pitch default)
        "-ac", "1",      # Mono
        audio_path
    ], check=True, capture_output=True)

    return audio_path, title


def transcribe_audio(audio_path: str) -> list[dict]:
    """
    Transcribe audio to MIDI notes using basic-pitch.

    Returns: List of {start, duration, midi_pitch}
    """
    from basic_pitch.inference import predict

    model_output, midi_data, note_events = predict(audio_path)

    # note_events is a list of (start_time, end_time, pitch, velocity, [pitch_bend])
    notes = []
    for event in note_events:
        start_time = event[0]
        end_time = event[1]
        pitch = int(event[2])

        notes.append({
            "start": start_time,
            "duration": end_time - start_time,
            "midi_pitch": pitch,
        })

    # Sort by start time
    notes.sort(key=lambda n: (n["start"], n["midi_pitch"]))
    return notes


def find_string_fret_options(midi_pitch: int) -> list[tuple[int, int]]:
    """
    Find all valid (string, fret) combinations for a MIDI pitch.
    Returns list of (string, fret) tuples, sorted by fret (prefer lower frets).
    """
    options = []
    for string, open_pitch in STANDARD_TUNING.items():
        fret = midi_pitch - open_pitch
        if 0 <= fret <= MAX_FRET:
            options.append((string, fret))
    # Sort by fret (prefer lower positions)
    options.sort(key=lambda x: x[1])
    return options


def viterbi_string_fret(notes: list[dict]) -> list[TabNote]:
    """
    Assign string and fret to each note using Viterbi dynamic programming.

    Cost function:
    cost = |fret_now - fret_prev| + 2*|string_now - string_prev| + 0.3*fret

    Handles chords by grouping simultaneous notes (within 50ms).
    """
    import numpy as np

    if not notes:
        return []

    # Group notes into time slices (chords if within threshold)
    slices = []
    current_slice = [notes[0]]

    for note in notes[1:]:
        if note["start"] - current_slice[0]["start"] <= CHORD_TIME_THRESHOLD:
            current_slice.append(note)
        else:
            slices.append(current_slice)
            current_slice = [note]
    slices.append(current_slice)

    # Process each slice
    result = []
    prev_assignments = []  # List of (string, fret) from previous slice

    for slice_notes in slices:
        # For each note in the chord, find best assignment
        # Greedy approach: assign bass notes to lower strings first
        slice_notes_sorted = sorted(slice_notes, key=lambda n: n["midi_pitch"])

        used_strings = set()
        slice_assignments = []

        for note in slice_notes_sorted:
            options = find_string_fret_options(note["midi_pitch"])

            if not options:
                # Note is out of range, skip it
                continue

            # Filter out already-used strings for this chord
            available_options = [opt for opt in options if opt[0] not in used_strings]
            if not available_options:
                available_options = options  # Fall back if all strings used

            # Calculate cost for each option
            best_option = None
            best_cost = float("inf")

            for string, fret in available_options:
                # Base cost: prefer lower frets
                cost = 0.3 * fret

                # Cost from previous slice (position change penalty)
                if prev_assignments:
                    min_prev_cost = float("inf")
                    for prev_string, prev_fret in prev_assignments:
                        prev_cost = abs(fret - prev_fret) + 2 * abs(string - prev_string)
                        min_prev_cost = min(min_prev_cost, prev_cost)
                    cost += min_prev_cost

                if cost < best_cost:
                    best_cost = cost
                    best_option = (string, fret)

            if best_option:
                string, fret = best_option
                used_strings.add(string)
                slice_assignments.append((string, fret))

                result.append(TabNote(
                    start=note["start"],
                    duration=note["duration"],
                    midi_pitch=note["midi_pitch"],
                    string=string,
                    fret=fret,
                ))

        if slice_assignments:
            prev_assignments = slice_assignments

    return result


def duration_to_note_type(duration: float, tempo: int = 120) -> tuple[str, int]:
    """
    Convert duration in seconds to MusicXML note type and divisions.

    Returns: (note_type, divisions)
    """
    # At 120 BPM, quarter note = 0.5 seconds
    beat_duration = 60.0 / tempo

    # Duration as fraction of a quarter note
    quarter_notes = duration / beat_duration

    # Divisions per quarter note (we use 4)
    divisions_per_quarter = 4
    divisions = round(quarter_notes * divisions_per_quarter)
    divisions = max(1, min(divisions, 16))  # Clamp to reasonable range

    # Determine note type
    if quarter_notes >= 3.5:
        note_type = "whole"
    elif quarter_notes >= 1.5:
        note_type = "half"
    elif quarter_notes >= 0.75:
        note_type = "quarter"
    elif quarter_notes >= 0.375:
        note_type = "eighth"
    else:
        note_type = "16th"

    return note_type, divisions


def generate_musicxml(tab_notes: list[TabNote], title: str) -> str:
    """
    Generate MusicXML 4.0 document with TAB notation.
    """
    # Sort notes by start time
    tab_notes = sorted(tab_notes, key=lambda n: (n.start, n.string))

    if not tab_notes:
        # Return empty score
        tab_notes = []

    # Create MusicXML structure
    root = ET.Element("score-partwise", version="4.0")

    # Work element (title)
    work = ET.SubElement(root, "work")
    work_title = ET.SubElement(work, "work-title")
    work_title.text = title

    # Identification
    identification = ET.SubElement(root, "identification")
    creator = ET.SubElement(identification, "creator", type="software")
    creator.text = "TabPaste"

    # Part list
    part_list = ET.SubElement(root, "part-list")
    score_part = ET.SubElement(part_list, "score-part", id="P1")
    part_name = ET.SubElement(score_part, "part-name")
    part_name.text = "Guitar"

    # Part with measures
    part = ET.SubElement(root, "part", id="P1")

    # Settings
    tempo = 120
    divisions_per_quarter = 4
    beats_per_measure = 4
    beat_type = 4

    # Duration of one measure in seconds
    beat_duration = 60.0 / tempo
    measure_duration = beats_per_measure * beat_duration

    # Group notes into measures
    if tab_notes:
        total_duration = max(n.start + n.duration for n in tab_notes)
        num_measures = max(1, int(total_duration / measure_duration) + 1)
    else:
        num_measures = 1

    for measure_num in range(1, num_measures + 1):
        measure = ET.SubElement(part, "measure", number=str(measure_num))

        # Attributes (only in first measure)
        if measure_num == 1:
            attributes = ET.SubElement(measure, "attributes")

            div = ET.SubElement(attributes, "divisions")
            div.text = str(divisions_per_quarter)

            time_elem = ET.SubElement(attributes, "time")
            beats = ET.SubElement(time_elem, "beats")
            beats.text = str(beats_per_measure)
            beat_type_elem = ET.SubElement(time_elem, "beat-type")
            beat_type_elem.text = str(beat_type)

            # TAB clef
            clef = ET.SubElement(attributes, "clef")
            sign = ET.SubElement(clef, "sign")
            sign.text = "TAB"
            line = ET.SubElement(clef, "line")
            line.text = "5"

            # Staff details for 6-string guitar
            staff_details = ET.SubElement(attributes, "staff-details")
            staff_lines = ET.SubElement(staff_details, "staff-lines")
            staff_lines.text = "6"

            # Add string tunings
            for string_num in range(1, 7):
                staff_tuning = ET.SubElement(staff_details, "staff-tuning", line=str(string_num))
                tuning_step = ET.SubElement(staff_tuning, "tuning-step")
                tuning_octave = ET.SubElement(staff_tuning, "tuning-octave")

                # Map string to pitch
                pitches = {1: ("E", 4), 2: ("B", 3), 3: ("G", 3),
                          4: ("D", 3), 5: ("A", 2), 6: ("E", 2)}
                step, octave = pitches[string_num]
                tuning_step.text = step
                tuning_octave.text = str(octave)

            # Direction with tempo
            direction = ET.SubElement(measure, "direction", placement="above")
            direction_type = ET.SubElement(direction, "direction-type")
            metronome = ET.SubElement(direction_type, "metronome")
            beat_unit = ET.SubElement(metronome, "beat-unit")
            beat_unit.text = "quarter"
            per_minute = ET.SubElement(metronome, "per-minute")
            per_minute.text = str(tempo)

        # Get notes for this measure
        measure_start = (measure_num - 1) * measure_duration
        measure_end = measure_num * measure_duration

        measure_notes = [n for n in tab_notes
                        if measure_start <= n.start < measure_end]

        if not measure_notes:
            # Add rest for empty measure
            note = ET.SubElement(measure, "note")
            rest = ET.SubElement(note, "rest")
            duration = ET.SubElement(note, "duration")
            duration.text = str(divisions_per_quarter * beats_per_measure)
            note_type = ET.SubElement(note, "type")
            note_type.text = "whole"
            continue

        # Sort by start time, then by string (to handle chords)
        measure_notes.sort(key=lambda n: (n.start, n.string))

        # Track timing within measure
        current_time = 0  # In divisions
        total_measure_divisions = divisions_per_quarter * beats_per_measure

        # Group simultaneous notes
        i = 0
        while i < len(measure_notes):
            note_obj = measure_notes[i]

            # Calculate position in measure
            note_position_in_measure = note_obj.start - measure_start
            note_position_divisions = int(note_position_in_measure / beat_duration * divisions_per_quarter)

            # Add forward element if there's a gap
            if note_position_divisions > current_time:
                forward = ET.SubElement(measure, "forward")
                forward_duration = ET.SubElement(forward, "duration")
                forward_duration.text = str(note_position_divisions - current_time)
                current_time = note_position_divisions

            # Find all notes at the same time (chord)
            chord_notes = [note_obj]
            j = i + 1
            while j < len(measure_notes):
                if abs(measure_notes[j].start - note_obj.start) <= CHORD_TIME_THRESHOLD:
                    chord_notes.append(measure_notes[j])
                    j += 1
                else:
                    break

            # Write chord notes
            for idx, chord_note in enumerate(chord_notes):
                note = ET.SubElement(measure, "note")

                # Add chord marker for 2nd+ notes
                if idx > 0:
                    ET.SubElement(note, "chord")

                # Pitch
                pitch = ET.SubElement(note, "pitch")
                midi = chord_note.midi_pitch
                # Convert MIDI to pitch name
                pitch_names = ["C", "C", "D", "D", "E", "F", "F", "G", "G", "A", "A", "B"]
                alterations = [0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0]
                step = ET.SubElement(pitch, "step")
                step.text = pitch_names[midi % 12]
                if alterations[midi % 12]:
                    alter = ET.SubElement(pitch, "alter")
                    alter.text = "1"
                octave = ET.SubElement(pitch, "octave")
                octave.text = str(midi // 12 - 1)

                # Duration
                note_type_str, dur_divisions = duration_to_note_type(chord_note.duration, tempo)
                duration = ET.SubElement(note, "duration")
                duration.text = str(dur_divisions)

                # Type
                ntype = ET.SubElement(note, "type")
                ntype.text = note_type_str

                # Notations with technical (string/fret)
                notations = ET.SubElement(note, "notations")
                technical = ET.SubElement(notations, "technical")
                string_elem = ET.SubElement(technical, "string")
                string_elem.text = str(chord_note.string)
                fret_elem = ET.SubElement(technical, "fret")
                fret_elem.text = str(chord_note.fret)

            # Update current time
            _, dur_divisions = duration_to_note_type(chord_notes[0].duration, tempo)
            current_time += dur_divisions

            i = j  # Skip processed chord notes

        # Fill remaining time in measure with backup if needed
        # (MusicXML will handle this)

    # Generate XML string
    ET.indent(root, space="  ")
    xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
    doctype = '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">\n'
    xml_content = ET.tostring(root, encoding="unicode")

    return xml_declaration + doctype + xml_content


@app.function(image=image, secrets=[supabase_secret], timeout=600)
@modal.fastapi_endpoint(method="POST")
def process(job_id: str, youtube_url: str):
    """
    Main processing endpoint.

    Pipeline:
    1. Download audio from YouTube
    2. Transcribe to MIDI notes using basic-pitch
    3. Assign strings/frets using Viterbi DP
    4. Generate MusicXML
    5. Upload to Supabase Storage
    """
    import traceback

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Step 1: Download audio
            update_job_status(job_id, "processing", "Downloading audio from YouTube...")
            audio_path, title = download_audio(youtube_url, tmpdir)

            # Update title in database
            client = get_supabase_client()
            client.table("jobs").update({"video_title": title}).eq("id", job_id).execute()

            # Step 2: Transcribe
            update_job_status(job_id, "processing", "Transcribing audio to notes...")
            notes = transcribe_audio(audio_path)

            if not notes:
                raise ValueError("No notes detected in the audio. Make sure this is a solo guitar recording.")

            # Step 3: Viterbi string assignment
            update_job_status(job_id, "processing", f"Assigning strings and frets to {len(notes)} notes...")
            tab_notes = viterbi_string_fret(notes)

            # Step 4: Generate MusicXML
            update_job_status(job_id, "processing", "Generating tablature...")
            musicxml = generate_musicxml(tab_notes, title)

            # Step 5: Upload to Supabase Storage
            update_job_status(job_id, "processing", "Saving tablature...")
            musicxml_path = f"{job_id}.musicxml"

            client = get_supabase_client()
            client.storage.from_("tabs").upload(
                path=musicxml_path,
                file=musicxml.encode("utf-8"),
                file_options={"content-type": "application/vnd.recordare.musicxml+xml"}
            )

            # Mark as done
            update_job_status(job_id, "done", "Tablature ready!", musicxml_path=musicxml_path)

            return {"status": "success", "job_id": job_id}

    except Exception as e:
        error_msg = str(e)
        traceback.print_exc()
        update_job_status(job_id, "failed", error=error_msg)
        return {"status": "error", "error": error_msg}


# Local testing entry point
if __name__ == "__main__":
    # For local testing
    print("Deploy with: modal deploy app.py")
    print("Test with: modal run app.py")
