# -*- coding: utf-8 -*-
"""
Created on Thu Feb 19 20:06:33 2026

@author: Carlos Hernandez
"""

import random

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

def build_participants(file_list):

    participants = {}

    chaperone_file = open("chaperones.txt", "w")

    for file_name in file_list:

        file = open(file_name, "r")

        lines = file.readlines()

        # Skip first two rows
        for line in lines[2:]:

            line = line.strip()

            if line == "":
                continue

            data = line.split(";")

            # Skip rows that are just ;;;;;;;
            if len(data) < 8 or data[0] == "":
                continue

            school = data[0]
            role = data[1]
            name = data[2]
            email = data[3]
            grade = data[4]
            pref1 = data[5]
            pref2 = data[6]
            pref3 = data[7]
            empty = "Not Assigned"

            # STUDENTS
            if role == "Student":

                if school not in participants:
                    participants[school] = {}

                participants[school][name] = {
                    "grade": grade,
                    "email": email,
                    "preference_1": pref1,
                    "preference_2": pref2,
                    "preference_3": pref3,
                    "session_1": empty,
                    "session_2": empty,
                    "session_3": empty,
                    "session_4": empty,
                    "vendor": "No",
                    "preferred":"No"
                }

            # CHAPERONES
            elif role == "Chaperone":

                chaperone_file.write(school + "," + name + "\n")

        file.close()
    
    chaperone_file.close()
    return participants


def build_speakers(file_name):

    speakers = {}

    file = open(file_name, "r")

    lines = file.readlines()

    # Skip first two rows
    for line in lines[2:]:

        line = line.strip()

        if line == "":
            continue

        data = line.split(",")

        # Skip rows that are just ;;;;;;;
        if len(data) < 7 or data[0] == "":
            continue

        title = data[0]
        category = data[1]
        name = data[2]
        session = data[3]
        place = data[4]
        target = data[5]


        if session not in speakers:
            speakers[session] = {}
            speakers[session]["vendors"] = {
            "speaker_name":"vendors",
            "category":"N/A",
            "location":"PENDING",
            "target": "Everyone",
            "students" : []}

        speakers[session][title] = {
            "speaker_name":name,
            "category":category,
            "location":place,
            "target":target,
            "students" : []
            }
            
    return speakers


def assignment(participants: dict, speakers: dict, tolerance_percent: int):

    tolerance = tolerance_percent / 100

    # Collect all students
    all_students = []
    for school in participants:
        for name in participants[school]:
            all_students.append((school, name))

    session_names = list(speakers.keys())

    # ---------------------------------------------------
    # STEP 1 — EVEN VENDOR DISTRIBUTION (HIGH SCHOOL ONLY)
    # ---------------------------------------------------
    high_school_students = [
        (school, name)
        for school, name in all_students
        if participants[school][name]["grade"] != "6 to 8"
    ]

    random.shuffle(high_school_students)

    for i, (school, name) in enumerate(high_school_students):
        session = session_names[i % len(session_names)]
        participants[school][name][session] = "vendors"
        speakers[session]["vendors"]["students"].append(name + "," + school)

    # ---------------------------------------------------
    # STEP 2 — SESSION ASSIGNMENTS
    # ---------------------------------------------------
    for session in session_names:

        session_data = speakers[session]

        # Identify 6–8 title (if exists)
        middle_title = None
        for title in session_data:
            if session_data[title]["target"] == "6 to 8":
                middle_title = title
                break

        # Titles eligible for balancing (high school only)
        high_titles = [
            t for t in session_data
            if t != "vendors"
            and session_data[t]["target"] != "6 to 8"
        ]

        random.shuffle(all_students)

        for school, name in all_students:

            student = participants[school][name]

            # Skip already assigned (vendors from Step 1)
            if student[session] != "Not Assigned":
                continue

            # ---------------------------------------------------
            # 6–8 STUDENTS
            # ---------------------------------------------------
            if student["grade"] == "6 to 8":

                # If session has 6–8 title → assign there
                if middle_title is not None:
                    student[session] = middle_title
                    session_data[middle_title]["students"].append(name + "," + school)

                # If no 6–8 title → send to vendors
                else:
                    student[session] = "vendors"
                    session_data["vendors"]["students"].append(name + "," + school)

                continue

            # ---------------------------------------------------
            # HIGH SCHOOL STUDENTS (9–12)
            # ---------------------------------------------------
            titles_received = [
                student[s] for s in session_names
                if student[s] != "Not Assigned"
            ]

            assigned = False

            # Try preference match first
            for title in high_titles:

                if title in titles_received:
                    continue

                category = session_data[title]["category"]

                if category in (
                    student["preference_1"],
                    student["preference_2"],
                    student["preference_3"],
                ):
                    student[session] = title
                    session_data[title]["students"].append(name + "," + school)
                    student["_pref_assigned_" + session] = True
                    assigned = True
                    break

            # If no preference match → smallest group
            if not assigned:

                smallest_title = min(
                    high_titles,
                    key=lambda t: len(session_data[t]["students"])
                )

                student[session] = smallest_title
                session_data[smallest_title]["students"].append(name + "," + school)
                student["_pref_assigned_" + session] = False

        # ---------------------------------------------------
        # STEP 3 — REBALANCING (HIGH SCHOOL ONLY)
        # ---------------------------------------------------
        while True:

            counts = {
                t: len(session_data[t]["students"])
                for t in high_titles
            }

            if not counts:
                break

            max_title = max(counts, key=counts.get)
            min_title = min(counts, key=counts.get)

            max_size = counts[max_title]
            min_size = counts[min_title]

            if max_size <= min_size * (1 + tolerance):
                break

            moved = False

            for student_id in session_data[max_title]["students"]:

                name, school = student_id.split(",")
                student = participants[school][name]

                if not student.get("_pref_assigned_" + session, False):

                    session_data[max_title]["students"].remove(student_id)
                    session_data[min_title]["students"].append(student_id)
                    student[session] = min_title
                    moved = True
                    break

            if not moved:

                student_id = session_data[max_title]["students"][-1]

                name, school = student_id.split(",")
                student = participants[school][name]

                session_data[max_title]["students"].remove(student_id)
                session_data[min_title]["students"].append(student_id)
                student[session] = min_title

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

            # ---------------- LOGOS ----------------
            logo_table = Table([
                [
                    Image("NU_Logo.png", width=0.9*inch, height=0.9*inch),
                    Image("Conference_Logo.png", width=1.2*inch, height=1.2*inch),
                    Image("Ostapenko_logo.png", width=0.9*inch, height=0.9*inch)
                ]
            ], colWidths=[2*inch, 2*inch, 2*inch])

            logo_table.setStyle(TableStyle([
                ("ALIGN", (0,0), (-1,-1), "CENTER")
            ]))

            elements.append(logo_table)
            elements.append(Spacer(1, 0.25 * inch))

            # ---------------- TITLE ----------------
            elements.append(Paragraph("Youth Action Conference 2026", title_style))
            elements.append(Spacer(1, 0.2 * inch))

            # ---------------- SESSION INFO BOX ----------------
            info_table = Table([
                ["Session", session],
                ["Title", title],
                ["Speaker", speaker_info["speaker_name"]],
                ["Category", speaker_info["category"]],
                ["Room", speaker_info["location"]],
                ["Target", speaker_info["target"]]
            ], colWidths=[1.5*inch, 4.5*inch])

            info_table.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#A3C6D4")),
                ("BACKGROUND", (1,0), (1,-1), colors.whitesmoke),
                ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
            ]))

            elements.append(info_table)
            elements.append(Spacer(1, 0.35 * inch))

            # ---------------- STUDENT TABLE ----------------
            table_data = [["Student Name", "School"]]

            sorted_students = sorted(speaker_info["students"])

            for student_id in sorted_students:
                name, school = student_id.split(",")
                table_data.append([name, school])

            if len(table_data) == 1:
                table_data.append(["No students assigned", "-"])

            table = Table(
                table_data,
                colWidths=[3*inch, 2*inch]
            )

            table.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#592C82")),
                ("TEXTCOLOR", (0,0), (-1,0), colors.white),

                ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.whitesmoke, colors.lightgrey]),

                ("GRID", (0,0), (-1,-1), 0.5, colors.grey),

                ("FONTSIZE", (0,0), (-1,-1), 9),
                ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
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
                    Image("NU_Logo.png", width=0.9*inch, height=0.9*inch),
                    Image("Conference_Logo.png", width=1.2*inch, height=1.2*inch),
                    Image("Ostapenko_logo.png", width=0.9*inch, height=0.9*inch)
                ]
            ], colWidths=[2*inch, 2*inch, 2*inch])

            logo_table.setStyle(TableStyle([
                ("ALIGN", (0,0), (-1,-1), "CENTER")
            ]))

            elements.append(logo_table)
            elements.append(Spacer(1, 0.25 * inch))

            # ---------------- TITLE ----------------
            elements.append(Paragraph("Youth Action Conference 2026", title_style))

            # just clean white space instead of divider
            elements.append(Spacer(1, 0.2 * inch))

            # ---------------- STUDENT INFO BOX ----------------
            info_table = Table([
                ["Student", student_name],
                ["School", school],
                ["Grade", student["grade"]]
            ], colWidths=[1.5*inch, 4.5*inch])

            info_table.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#A3C6D4")),
                ("BACKGROUND", (1,0), (1,-1), colors.whitesmoke),
                ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
            ]))

            elements.append(info_table)
            elements.append(Spacer(1, 0.35 * inch))

            # ---------------- SCHEDULE TABLE ----------------
            table_data = [["Time", "Session", "Room", "Speaker"]]

            for i in range(len(session_names)):

                session = session_names[i]
                assigned_title = student[session]

                if assigned_title == "vendors":
                    title = "Vendor Exploration"
                    room = "Grand Foyer"
                    speaker_name = "Vendors"
                else:
                    session_info = speakers[session][assigned_title]
                    title = assigned_title
                    room = session_info["location"]
                    speaker_name = session_info["speaker_name"]

                table_data.append([
                    time_blocks[i],
                    title,
                    room,
                    speaker_name
                ])

            table = Table(
                table_data,
                colWidths=[1.5*inch, 2.5*inch, 1.2*inch, 1.5*inch]
            )

            table.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#592C82")),
                ("TEXTCOLOR", (0,0), (-1,0), colors.white),

                ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.whitesmoke, colors.lightgrey]),

                ("GRID", (0,0), (-1,-1), 0.5, colors.grey),

                ("FONTSIZE", (0,0), (-1,-1), 9),
                ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ]))

            elements.append(table)
            elements.append(PageBreak())

        doc.build(elements)

    print("PDF files generated successfully.")


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
            print(title, ":", count)

            if title == "vendors":
                continue

            counts.append(count)

            if speakers[session][title]["target"] == "6 to 8":
                middle_counts.append(count)

            for student_id in speakers[session][title]["students"]:

                name, school = student_id.split(",")
                student = participants[school][name]

                # High school only
                if student["grade"] != "6 to 8":

                    total_high += 1

                    category = speakers[session][title]["category"]

                    if category in (
                        student["preference_1"],
                        student["preference_2"],
                        student["preference_3"],
                    ):
                        preference_matches += 1

        # Talk distribution statistics
        if counts:
            print("Talk Min:", min(counts))
            print("Talk Max:", max(counts))
            print("Talk Difference:", max(counts) - min(counts))
            print("Talk Average:", round(sum(counts) / len(counts), 2))

        if total_high > 0:
            percent = round((preference_matches / total_high) * 100, 2)
            print("High School Preference Satisfaction:", percent, "%")

        if middle_counts:
            print("6–8 Title Size:", middle_counts[0])

    # ======================================================
    # OVERALL DAY PREFERENCE SUMMARY (HIGH SCHOOL ONLY)
    # ======================================================

    print("\n==============================")
    print("OVERALL DAY PREFERENCE SUMMARY")
    print("==============================")

    high_school_students = []

    for school in participants:
        for name in participants[school]:
            if participants[school][name]["grade"] != "6 to 8":
                high_school_students.append((school, name))

    total_students = len(high_school_students)

    three = 0
    two = 0
    one = 0
    zero = 0

    for school, name in high_school_students:

        student = participants[school][name]
        preference_hits = 0

        for session in speakers:

            assigned_title = student[session]

            if assigned_title == "vendors":
                continue

            category = speakers[session][assigned_title]["category"]

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
    
    """Make sure they use ;"""
    file_list = ["School_Registration_Test1.csv",
                 "School_Registration_Test2.csv"]
    
    """Make sure this use , """
    speaker_file = "Speakers.csv"
    
    participants = build_participants(file_list)
    speakers = build_speakers(speaker_file)
    
    participants, speakers = assignment(participants, speakers, 20)
    analyze_fairness(participants , speakers)
    
    generate_session_pdfs(participants, speakers)
    generate_school_pdfs_option1(participants, speakers)
    
    return None
    
init()
