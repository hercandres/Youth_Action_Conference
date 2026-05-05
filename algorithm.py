# -*- coding: utf-8 -*-
"""
Created on Thu Feb 19 20:06:33 2026

@author: Carlos Hernandez
"""

import random
import os

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import Table, TableStyle
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch


# Helper: returns True if the grade string is middle school
# Accepts both "7 or 8" and the CSV value "6 to 8"
def is_middle(grade):
    return grade in ("7 or 8", "6 to 8")

# Helper: returns True if the grade string is high school
def is_high(grade):
    return grade in ("9 or 10", "11 or 12")


def build_participants(file_list):
    """
    Reads every school CSV using Python's csv module so that quoted fields
    containing commas (e.g. email addresses with embedded newlines, titles
    with commas) are parsed correctly.
    """
    import csv

    participants = {}

    chaperone_file = open("chaperones.txt", "w")

    for file_name in file_list:

        with open(file_name, "r", newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)

            rows = list(reader)

        # Skip first two header/instruction rows
        for row in rows[2:]:

            # Pad short rows so index access is always safe
            while len(row) < 8:
                row.append("")

            if row[0].strip() == "":
                continue

            # Strip every field
            school = row[0].strip()
            role   = row[1].strip()
            name   = row[2].strip()
            email  = row[3].strip().replace("\n", "").replace("\r", "")
            grade  = row[4].strip()
            pref1  = row[5].strip()
            pref2  = row[6].strip()
            pref3  = row[7].strip()
            empty  = "Not Assigned"

            # Normalize single-number grades → range strings
            if grade in ("9", "10"):
                grade = "9 or 10"
            elif grade in ("11", "12"):
                grade = "11 or 12"

            # STUDENTS (case-insensitive)
            if role.lower() == "student":

                if school not in participants:
                    participants[school] = {}

                participants[school][name] = {
                    "grade":        grade,
                    "email":        email,
                    "preference_1": pref1,
                    "preference_2": pref2,
                    "preference_3": pref3,
                    "Session 1":    empty,
                    "Session 2":    empty,
                    "Session 3":    empty,
                    "Session 4":    empty,
                    "vendor":       "No",
                    "preferred":    "No"
                }

            # CHAPERONES (case-insensitive)
            elif role.lower() == "chaperone":
                chaperone_file.write(school + "," + name + "\n")

    chaperone_file.close()
    return participants


def build_speakers(file_name):
    """
    Builds the speakers dict from the CSV.

    FIX: If a title already exists in a session, a numeric suffix is appended
    (e.g. "Exclusion Workshop", "Exclusion Workshop_2", "Exclusion Workshop_3")
    so that no talk silently overwrites another.  The original title string is
    stored under the key "base_title" so the PDFs can still display the clean name.
    """

    # Pre-initialize all 4 sessions so the assignment loop never hits a KeyError
    # even if a session has no talks listed in the speakers CSV.
    ALL_SESSIONS = ["Session 1", "Session 2", "Session 3", "Session 4"]

    speakers = {}
    for s in ALL_SESSIONS:
        speakers[s] = {
            "vendors": {
                "base_title":   "vendors",
                "speaker_name": "vendors",
                "category":     "N/A",
                "location":     "PENDING",
                "target":       "Everyone",
                "students":     []
            }
        }

    # Try the filename as-is first, then with a .csv extension
    if not os.path.exists(file_name) and os.path.exists(file_name + ".csv"):
        file_name = file_name + ".csv"

    # Use csv.reader so quoted fields with commas parse correctly
    import csv

    with open(file_name, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)

    # Skip first two header/instruction rows
    for row in rows[2:]:

        while len(row) < 6:
            row.append("")

        if row[0].strip() == "":
            continue

        # Strip every field
        title    = row[0].strip()
        category = row[1].strip()
        name     = row[2].strip()
        session  = row[3].strip()
        place    = row[4].strip()
        target   = row[5].strip()

        # Normalize session name: "session_1" -> "Session 1" etc.
        session = session.replace("session_", "Session ").replace("Session_", "Session ")
        # Handle edge case like "session1" with no underscore
        for n in ("1","2","3","4"):
            if session.lower().replace(" ","") == "session" + n:
                session = "Session " + n

        # Skip the "Vendors" row — already pre-initialized as "vendors"
        if title.lower() == "vendors":
            continue

        # Skip rows whose session name is not one of the 4 expected sessions
        if session not in speakers:
            print(f"WARNING: Unrecognised session '{session}' for talk '{title}' — skipped.")
            continue

        # Make the key unique if this title already exists in this session
        unique_title = title
        suffix = 2
        while unique_title in speakers[session]:
            unique_title = f"{title}_{suffix}"
            suffix += 1
        # ───────────────────────────────────────────────────────────────────

        speakers[session][unique_title] = {
            "base_title":   title,          # original readable name for PDFs
            "speaker_name": name,
            "category":     category,
            "location":     place,
            "target":       target,
            "students":     []
        }

    return speakers


def assignment(participants: dict, speakers: dict, tolerance_percent: int):

    tolerance = tolerance_percent / 100

    # ⚠️  Must exactly match the school name as it appears in your CSV.
    BUFFALO_SCHOOL = "Buffalo Public School.csv"

    session_names = ["Session 1", "Session 2", "Session 3", "Session 4"]

    all_students = []
    for school in participants:
        for name in participants[school]:
            all_students.append((school, name))

    # ---------------------------------------------------
    # FIX: Build a "seen categories" tracker so that no
    # student ever attends two talks in the same category
    # (e.g. two "Mental Health" workshops across sessions).
    # ---------------------------------------------------
    seen_categories = {
        name + "||" + school: set()
        for school in participants
        for name in participants[school]
    }

    # ---------------------------------------------------
    # STEP 0 — LOCK BUFFALO INTO SESSION 4 EVENT CENTER
    # ---------------------------------------------------
    for school, name in all_students:

        if school == BUFFALO_SCHOOL:

            student = participants[school][name]
            student["Session 4"] = "Event Center"

            speakers["Session 4"]["Event Center"]["students"].append(
                name + "||" + school
            )

    # ---------------------------------------------------
    # VENDOR SETUP
    # ---------------------------------------------------
    vendor_counts = {s: 0 for s in session_names}
    buffalo_vendor_seen = {}

    for school, name in all_students:
        if school == BUFFALO_SCHOOL:
            buffalo_vendor_seen[name + "||" + school] = False

    random.shuffle(all_students)

    # ---------------------------------------------------
    # STEP 1 — VENDORS (SESSIONS 1–3 ONLY)
    # ---------------------------------------------------
    for school, name in all_students:

        student = participants[school][name]
        student_id = name + "||" + school

        for session in ["Session 1", "Session 2", "Session 3"]:

            if student[session] != "Not Assigned":
                continue

            # ---------------- BUFFALO (RANDOMIZED) ----------------
            if school == BUFFALO_SCHOOL:

                if (not buffalo_vendor_seen[student_id]
                        and random.random() < 0.30):

                    student[session] = "vendors"
                    speakers[session]["vendors"]["students"].append(student_id)
                    vendor_counts[session] += 1

                    buffalo_vendor_seen[student_id] = True

                continue

            # ---------------- OTHER SCHOOLS ----------------
            # Break after assigning so the student only gets ONE vendor slot
            if random.random() < 0.15:
                student[session] = "vendors"
                speakers[session]["vendors"]["students"].append(student_id)
                vendor_counts[session] += 1
                break

    # ---------------------------------------------------
    # GUARANTEE: EVERY STUDENT HAS ≥1 VENDOR VISIT
    #
    # Buffalo students  → must land in Sessions 1–3
    #   (Session 4 is locked to Buffalo Elections)
    # All other students → Sessions 1–4 are all eligible
    # ---------------------------------------------------
    for school, name in all_students:

        student_id = name + "||" + school
        student    = participants[school][name]

        if school == BUFFALO_SCHOOL:
            # Buffalo: check sessions 1-3 only
            eligible_sessions = ["Session 1", "Session 2", "Session 3"]
        else:
            # Everyone else: any session is fine
            eligible_sessions = ["Session 1", "Session 2", "Session 3", "Session 4"]

        has_vendor = any(student[s] == "vendors" for s in eligible_sessions)

        if not has_vendor:
            # Pick the session among eligible ones that is still unassigned,
            # preferring to avoid displacing an already-assigned workshop slot.
            unassigned = [s for s in eligible_sessions if student[s] == "Not Assigned"]
            pool = unassigned if unassigned else eligible_sessions
            chosen = random.choice(pool)

            # If this slot already had a workshop assigned, remove it from
            # that workshop's student list before overwriting.
            prev = student[chosen]
            if prev not in ("Not Assigned", "vendors"):
                prev_list = speakers[chosen][prev]["students"]
                if student_id in prev_list:
                    prev_list.remove(student_id)

            student[chosen] = "vendors"
            speakers[chosen]["vendors"]["students"].append(student_id)

    # ---------------------------------------------------
    # STEP 2 — NORMAL ASSIGNMENT (ALL SESSIONS)
    # ---------------------------------------------------
    for session in session_names:

        session_data = speakers[session]

        # ---------------- MIDDLE SCHOOL TITLE ----------------
        middle_title = None
        for title in session_data:
            if session_data[title].get("target") in ("7 or 8", "6 to 8"):
                middle_title = title
                break

        # ---------------- HIGH SCHOOL TITLES ----------------
        # "Event Center" excluded — only Buffalo goes there.
        high_titles = [
            t for t in session_data
            if t != "vendors"
            and t != "Event Center"
            and session_data[t].get("target") == "9 to 12"
        ]

        random.shuffle(all_students)

        for school, name in all_students:

            student    = participants[school][name]
            student_id = name + "||" + school

            # Already assigned (covers Buffalo in Session 4 and any vendor slots)
            if student[session] != "Not Assigned":
                continue

            # ---------------- MIDDLE SCHOOL ----------------
            if is_middle(student["grade"]):

                if middle_title:
                    student[session] = middle_title
                    session_data[middle_title]["students"].append(student_id)
                else:
                    # No middle-school talk this session → send to vendors
                    student[session] = "vendors"
                    session_data["vendors"]["students"].append(student_id)

                continue

            # ---------------- HIGH SCHOOL ----------------
            if not is_high(student["grade"]):
                continue

            assigned = False

            for title in high_titles:

                category = session_data[title]["category"]

                # FIX: only match if the student hasn't already attended
                # a talk in this category in a previous session.
                if (category in (
                        student["preference_1"],
                        student["preference_2"],
                        student["preference_3"])
                        and category not in seen_categories[student_id]):

                    student[session] = title
                    session_data[title]["students"].append(student_id)
                    seen_categories[student_id].add(category)   # mark seen
                    assigned = True
                    break

            if not assigned and high_titles:

                # Fall back to least-populated talk, still respecting
                # the "no repeat category" rule where possible.
                eligible = [
                    t for t in high_titles
                    if session_data[t]["category"] not in seen_categories[student_id]
                ]

                pool = eligible if eligible else high_titles

                smallest = min(pool, key=lambda t: len(session_data[t]["students"]))

                student[session] = smallest
                session_data[smallest]["students"].append(student_id)
                seen_categories[student_id].add(session_data[smallest]["category"])

    # ---------------------------------------------------
    # STEP 3 — REBALANCING
    # "Event Center" excluded — Buffalo stays locked.
    # ---------------------------------------------------
    for session in session_names:

        session_data = speakers[session]

        high_titles = [
            t for t in session_data
            if t != "vendors"
            and t != "Event Center"
            and session_data[t].get("target") == "9 to 12"
        ]

        while True:

            counts = {
                t: len(session_data[t]["students"])
                for t in high_titles
            }

            if not counts:
                break

            max_t = max(counts, key=counts.get)
            min_t = min(counts, key=counts.get)

            if counts[max_t] <= counts[min_t] * (1 + tolerance):
                break

            moved = False

            for student_id in session_data[max_t]["students"]:

                name, school = student_id.split("||", 1)
                student = participants[school][name]

                session_data[max_t]["students"].remove(student_id)
                session_data[min_t]["students"].append(student_id)

                student[session] = min_t
                moved = True
                break

            if not moved:
                break

    return participants, speakers


def generate_session_pdfs(participants, speakers):

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "title",
        parent=styles["Heading1"],
        textColor=colors.HexColor("#592C82"),
        alignment=1,
        spaceAfter=12
    )

    normal = styles["Normal"]

    for session in speakers:

        file_name = session + "_Overview.pdf"
        doc = SimpleDocTemplate(file_name)
        elements = []

        session_data = speakers[session]

        for title in session_data:

            speaker_info = session_data[title]

            # Use the original readable name for display
            display_title = speaker_info.get("base_title", title)

            # ---------------- LOGOS ----------------
            logo_table = Table([
                [
                    Image("NU_Logo.png",         width=0.9 * inch, height=0.9 * inch),
                    Image("Conference_Logo.png",  width=1.2 * inch, height=1.2 * inch),
                    Image("Ostapenko_logo.png",   width=0.9 * inch, height=0.9 * inch)
                ]
            ], colWidths=[2 * inch, 2 * inch, 2 * inch])

            logo_table.setStyle(TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER")
            ]))

            elements.append(logo_table)
            elements.append(Spacer(1, 0.25 * inch))

            # ---------------- TITLE ----------------
            elements.append(Paragraph("Youth Action Conference 2026", title_style))
            elements.append(Spacer(1, 0.2 * inch))

            # ---------------- SESSION INFO BOX ----------------
            info_table = Table([
                ["Session",  session],
                ["Title",    display_title],
                ["Speaker",  speaker_info["speaker_name"]],
                ["Category", speaker_info["category"]],
                ["Room",     speaker_info["location"]],
                ["Target",   speaker_info["target"]]
            ], colWidths=[1.5 * inch, 4.5 * inch])

            info_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#A3C6D4")),
                ("BACKGROUND", (1, 0), (1, -1), colors.whitesmoke),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ]))

            elements.append(info_table)
            elements.append(Spacer(1, 0.35 * inch))

            # ---------------- STUDENT TABLE ----------------
            table_data = [["Student Name", "School"]]

            sorted_students = sorted(speaker_info["students"])

            for student_id in sorted_students:
                name, school = student_id.split("||", 1)
                table_data.append([name, school])

            if len(table_data) == 1:
                table_data.append(["No students assigned", "-"])

            table = Table(
                table_data,
                colWidths=[3 * inch, 2 * inch]
            )

            table.setStyle(TableStyle([
                ("BACKGROUND",     (0, 0), (-1,  0), colors.HexColor("#592C82")),
                ("TEXTCOLOR",      (0, 0), (-1,  0), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),
                ("GRID",           (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTSIZE",       (0, 0), (-1, -1), 9),
                ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
            ]))

            elements.append(table)
            elements.append(PageBreak())

        doc.build(elements)

    print("Session overview PDFs generated successfully.")


def generate_school_pdfs_option1(participants, speakers):
    time_blocks = [
        "9:45 AM – 10:15 AM",
        "10:20 AM – 10:50 AM",
        "10:55 AM – 11:25 AM",
        "11:30 AM – 12:00 PM"
    ]

    session_names = list(speakers.keys())

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "title",
        parent=styles["Heading1"],
        textColor=colors.HexColor("#592C82"),
        alignment=1,
        spaceAfter=12
    )

    normal = styles["Normal"]

    for school in participants:

        file_name = school.replace(" ", "_") + "_Schedules.pdf"
        doc = SimpleDocTemplate(file_name)

        elements = []

        for student_name in participants[school]:

            student = participants[school][student_name]

            # ---------------- LOGOS ----------------
            logo_table = Table([
                [
                    Image("NU_Logo.png",         width=0.9 * inch, height=0.9 * inch),
                    Image("Conference_Logo.png",  width=1.2 * inch, height=1.2 * inch),
                    Image("Ostapenko_logo.png",   width=0.9 * inch, height=0.9 * inch)
                ]
            ], colWidths=[2 * inch, 2 * inch, 2 * inch])

            logo_table.setStyle(TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER")
            ]))

            elements.append(logo_table)
            elements.append(Spacer(1, 0.25 * inch))

            # ---------------- TITLE ----------------
            elements.append(Paragraph("Youth Action Conference 2026", title_style))

            elements.append(Spacer(1, 0.2 * inch))

            # ---------------- STUDENT INFO BOX ----------------
            info_table = Table([
                ["Student", student_name],
                ["School",  school],
                ["Grade",   student["grade"]]
            ], colWidths=[1.5 * inch, 4.5 * inch])

            info_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#A3C6D4")),
                ("BACKGROUND", (1, 0), (1, -1), colors.whitesmoke),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ]))

            elements.append(info_table)
            elements.append(Spacer(1, 0.35 * inch))

            # ---------------- SCHEDULE TABLE ----------------
            # Use Paragraph for all cells so long titles wrap cleanly
            cell_style = ParagraphStyle(
                "sched_cell",
                parent=styles["Normal"],
                fontSize=9,
                leading=11,
            )
            header_style = ParagraphStyle(
                "sched_header",
                parent=styles["Normal"],
                fontSize=9,
                leading=11,
                textColor=colors.white,
                fontName="Helvetica-Bold",
            )

            table_data = [[
                Paragraph("Time",    header_style),
                Paragraph("Session", header_style),
                Paragraph("Room",    header_style),
                Paragraph("Speaker", header_style),
            ]]

            for i in range(len(session_names)):

                session        = session_names[i]
                assigned_title = student[session]

                if assigned_title == "Not Assigned":
                    title        = "Not Assigned"
                    room         = "-"
                    speaker_name = "-"
                elif assigned_title == "vendors":
                    title        = "Vendor Exploration"
                    room         = "Grand Foyer"
                    speaker_name = "Vendors"
                else:
                    session_info = speakers[session][assigned_title]
                    title        = session_info.get("base_title", assigned_title)
                    room         = session_info["location"]
                    speaker_name = session_info["speaker_name"]

                table_data.append([
                    Paragraph(time_blocks[i], cell_style),
                    Paragraph(title,          cell_style),
                    Paragraph(room,           cell_style),
                    Paragraph(speaker_name,   cell_style),
                ])

            table = Table(
                table_data,
                colWidths=[1.5 * inch, 2.5 * inch, 1.2 * inch, 1.5 * inch]
            )

            table.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (-1,  0), colors.HexColor("#592C82")),
                ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),
                ("GRID",          (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING",    (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))

            elements.append(table)
            elements.append(PageBreak())

        doc.build(elements)

    print("PDF files generated successfully.")


def generate_name_tag_pdfs(participants, speakers):

    from reportlab.pdfgen import canvas as canvas_module
    from reportlab.platypus import Table, TableStyle, Paragraph
    from reportlab.lib import colors
    from reportlab.lib.colors import HexColor
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.pagesizes import LETTER

    styles = getSampleStyleSheet()

    # ── Brand colors ──────────────────────────────────────────────────────────
    PURPLE       = HexColor("#592C82")
    PURPLE_LIGHT = HexColor("#EFE0FF")
    PURPLE_PALE  = HexColor("#F7F0FF")
    WHITE        = colors.white
    DARK_GRAY    = HexColor("#2E2E2E")

    # ── Badge dimensions: 4.25" wide × 6" tall  (VERTICAL / PORTRAIT) ────────
    PAGE_W, PAGE_H = LETTER           # 612 × 792 pt
    TAG_W = 4.25 * 72                 # 306 pt
    TAG_H = 6.00 * 72                 # 432 pt

    # ── 2-up layout: side by side, top of badge exactly 1.5" from page top ─
    MARGIN_X = (PAGE_W - 2 * TAG_W) / 2
    MARGIN_Y = PAGE_H - (1.5 * 72) - TAG_H   # PDF y=0 is at the bottom

    BADGE_SLOTS = [
        (MARGIN_X,           MARGIN_Y),
        (MARGIN_X + TAG_W,   MARGIN_Y),
    ]

    ONE_PER_PAGE = (2 * TAG_W > PAGE_W) or (TAG_H > PAGE_H)

    # ── Section heights inside each badge ─────────────────────────────────────
    HEADER_H = 64.0
    FOOTER_H = 18.0
    BODY_H   = TAG_H - HEADER_H - FOOTER_H

    # ── Conference data ────────────────────────────────────────────────────────
    time_blocks   = ["9:45–10:15", "10:20–10:50", "10:55–11:25", "11:30–12:00"]
    session_names = list(speakers.keys())

    # ══════════════════════════════════════════════════════════════════════════
    #  COMBINED BADGE  (identity + schedule, single side)
    # ══════════════════════════════════════════════════════════════════════════
    def _draw_badge(c, bx, by, student_name, school, student):
        x, y  = bx, by
        W, H  = TAG_W, TAG_H
        display_name = student_name.replace("_", " ")

        # ── Background regions ─────────────────────────────────────────────
        c.setFillColor(PURPLE)
        c.rect(x, y + BODY_H + FOOTER_H, W, HEADER_H, stroke=0, fill=1)
        c.rect(x, y,                      W, FOOTER_H, stroke=0, fill=1)

        c.setFillColor(PURPLE_PALE)
        c.rect(x, y + FOOTER_H, W, BODY_H, stroke=0, fill=1)

        STRIP_H = BODY_H * 0.30
        STRIP_Y = y + FOOTER_H + BODY_H * 0.66
        c.setFillColor(PURPLE_LIGHT)
        c.rect(x + 1, STRIP_Y, W - 2, STRIP_H, stroke=0, fill=1)

        c.setStrokeColor(PURPLE)
        c.setLineWidth(1.5)
        c.rect(x, y, W, H, stroke=1, fill=0)

        # ── Logo pair (header) ─────────────────────────────────────────────
        LOGO_H   = 50.0
        NU_W     = LOGO_H
        CF_W     = LOGO_H * 1.10
        GAP_L    = 14.0
        total_lw = NU_W + GAP_L + CF_W
        lx = x + (W - total_lw) / 2
        ly = y + H - HEADER_H + (HEADER_H - LOGO_H) / 2

        c.drawImage("NU_Logo.png",          lx,                ly,
                    width=NU_W,  height=LOGO_H, mask='auto')
        c.drawImage("Conference_Logo.png",  lx + NU_W + GAP_L, ly,
                    width=CF_W,  height=LOGO_H, mask='auto')

        # ── Name ──────────────────────────────────────────────────────────
        name_fs = 24
        while (c.stringWidth(display_name, "Helvetica-Bold", name_fs) > W - 24
               and name_fs > 11):
            name_fs -= 1
        c.setFillColor(PURPLE)
        c.setFont("Helvetica-Bold", name_fs)
        name_y = STRIP_Y + STRIP_H * 0.55 - name_fs * 0.18
        c.drawCentredString(x + W / 2, name_y, display_name)

        # ── Separator + school ─────────────────────────────────────────────
        sep_y = STRIP_Y + STRIP_H * 0.20
        c.setStrokeColor(PURPLE)
        c.setLineWidth(0.75)
        c.line(x + 28, sep_y, x + W - 28, sep_y)

        school_y = y + FOOTER_H + BODY_H * 0.60
        c.setFillColor(DARK_GRAY)
        c.setFont("Helvetica", 9)
        c.drawCentredString(x + W / 2, school_y, school)

        # ── Schedule table ─────────────────────────────────────────────────
        TABLE_AREA_H = BODY_H * 0.56
        TABLE_AREA_Y = y + FOOTER_H + 4

        cell_style = ParagraphStyle("cb", parent=styles["Normal"],
            fontSize=8, leading=10, alignment=1)
        header_style = ParagraphStyle("hb", parent=styles["Normal"],
            fontSize=8, leading=10, alignment=1, textColor=WHITE)

        schedule_data = [[
            Paragraph("<b>Time</b>",    header_style),
            Paragraph("<b>Session</b>", header_style),
            Paragraph("<b>Room</b>",    header_style),
        ]]
        for j, session in enumerate(session_names):
            assigned_title = student[session]
            if assigned_title == "Not Assigned":
                session_display, room = "Not Assigned", "–"
            elif assigned_title == "vendors":
                session_display, room = "Vendors", "Grand Foyer"
            else:
                info            = speakers[session][assigned_title]
                # Use the original readable name on the badge
                session_display = info.get("base_title", assigned_title)
                room            = info["location"]
            schedule_data.append([
                Paragraph(time_blocks[j],   cell_style),
                Paragraph(session_display,  cell_style),
                Paragraph(room,             cell_style),
            ])

        sched = Table(schedule_data,
            colWidths=[0.95 * inch, 1.75 * inch, 1.00 * inch])
        sched.setStyle(TableStyle([
            ("BACKGROUND",     (0, 0), (-1,  0), PURPLE),
            ("TEXTCOLOR",      (0, 0), (-1,  0), WHITE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, HexColor("#F7F0FF")]),
            ("GRID",           (0, 0), (-1, -1), 0.4, HexColor("#C4A8E0")),
            ("ALIGN",          (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",     (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
        ]))

        tbl_w, tbl_h = sched.wrapOn(c, W - 20, TABLE_AREA_H)
        tbl_x = x + (W - tbl_w) / 2
        tbl_y = TABLE_AREA_Y + (TABLE_AREA_H - tbl_h) / 2
        sched.drawOn(c, tbl_x, tbl_y)

        # ── Footer text ────────────────────────────────────────────────────
        c.setFillColor(WHITE)
        c.setFont("Helvetica", 7)
        c.drawCentredString(x + W / 2, y + 5, "Youth Action Conference 2026")

    # ══════════════════════════════════════════════════════════════════════════
    #  MAIN LOOP
    # ══════════════════════════════════════════════════════════════════════════
    for school in participants:
        file_name = school.replace(" ", "_") + "_NameTags.pdf"
        c = canvas_module.Canvas(file_name, pagesize=LETTER)
        students = list(participants[school].keys())

        if ONE_PER_PAGE:
            cx = (PAGE_W - TAG_W) / 2
            cy = (PAGE_H - TAG_H) / 2
            for name in students:
                _draw_badge(c, cx, cy, name, school, participants[school][name])
                c.showPage()
        else:
            for i in range(0, len(students), 2):
                chunk = students[i : i + 2]
                for slot_idx, name in enumerate(chunk):
                    bx, by = BADGE_SLOTS[slot_idx]
                    _draw_badge(c, bx, by, name, school, participants[school][name])
                c.showPage()

        c.save()

    print("Name tag PDFs generated successfully.")


def analyze_fairness(participants, speakers):

    # ======================================================
    # SESSION-BY-SESSION ANALYSIS
    # ======================================================

    for session in speakers:

        print("\n", session)

        counts = []
        total_high = 0
        preference_matches = 0
        middle_counts = []

        for title in speakers[session]:

            count = len(speakers[session][title]["students"])
            display_title = speakers[session][title].get("base_title", title)
            print(display_title, ":", count)

            if title == "vendors":
                continue

            counts.append(count)

            if speakers[session][title].get("target") in ("7 or 8", "6 to 8"):
                middle_counts.append(count)

            for student_id in speakers[session][title]["students"]:

                name, school = student_id.split("||", 1)
                student = participants[school][name]

                assigned_title = student.get(session, "Not Assigned")

                if assigned_title == "Not Assigned":
                    continue

                if assigned_title not in speakers[session]:
                    continue

                if is_high(student["grade"]):

                    total_high += 1

                    category = speakers[session][assigned_title].get("category")

                    if category in (
                        student["preference_1"],
                        student["preference_2"],
                        student["preference_3"],
                    ):
                        preference_matches += 1

        if counts:
            print("Talk Min:", min(counts))
            print("Talk Max:", max(counts))
            print("Talk Difference:", max(counts) - min(counts))
            print("Talk Average:", round(sum(counts) / len(counts), 2))

        if total_high > 0:
            percent = round((preference_matches / total_high) * 100, 2)
            print("High School Preference Satisfaction:", percent, "%")

        if middle_counts:
            print("7–8 Title Size:", middle_counts[0])

    # ======================================================
    # OVERALL DAY PREFERENCE SUMMARY (HIGH SCHOOL ONLY)
    # ======================================================

    print("\n==============================")
    print("OVERALL DAY PREFERENCE SUMMARY")
    print("==============================")

    high_school_students = []

    for school in participants:
        for name in participants[school]:
            if is_high(participants[school][name]["grade"]):
                high_school_students.append((school, name))

    total_students = len(high_school_students)

    three = 0
    two   = 0
    one   = 0
    zero  = 0

    for school, name in high_school_students:

        student = participants[school][name]
        preference_hits = 0

        for session in speakers:

            assigned_title = student.get(session, "Not Assigned")

            if assigned_title == "Not Assigned":
                continue

            if assigned_title not in speakers[session]:
                continue

            if assigned_title == "vendors":
                continue

            category = speakers[session][assigned_title].get("category")

            if category in (
                student["preference_1"],
                student["preference_2"],
                student["preference_3"],
            ):
                preference_hits += 1

        if preference_hits == 3:
            three += 1
        elif preference_hits == 2:
            two += 1
        elif preference_hits == 1:
            one += 1
        else:
            zero += 1

    if total_students > 0:

        print("3 Preference Assignments:",
              round((three / total_students) * 100, 2), "%")

        print("2 Preference Assignments:",
              round((two / total_students) * 100, 2), "%")

        print("1 Preference Assignment:",
              round((one / total_students) * 100, 2), "%")

        print("0 Preference Assignments:",
              round((zero / total_students) * 100, 2), "%")


def init():

    # ⚠️  Files must use commas (,) as delimiters
    file_list = [
        
    ]

    # ⚠️  This file must use commas (,) as delimiters
    speaker_file = "Workshop Presenters"

    # ⚠️  These three image files must be in the same directory as this script
    required_images = ["NU_Logo.png", "Conference_Logo.png", "Ostapenko_logo.png"]
    for img in required_images:
        if not os.path.exists(img):
            print(f"WARNING: Missing image file '{img}' — PDFs will fail to build.")

    participants = build_participants(file_list)
    speakers     = build_speakers(speaker_file)

    participants, speakers = assignment(participants, speakers, 20)
    analyze_fairness(participants, speakers)

    generate_session_pdfs(participants, speakers)
    generate_school_pdfs_option1(participants, speakers)
    generate_name_tag_pdfs(participants, speakers)

    return None


init()
