"""Isolated browser-QA data; never writes to the user's primary study database."""
import hashlib
import json

from muj_study.core import App, ROOT


def seed():
    folder = ROOT / 'data' / 'responsive-qa'
    app = App(data=folder)
    try:
        source = folder / 'Long_course_document_with_extended_filename_for_responsive_layout_verification.txt'
        source.write_text('Inner joins combine matching rows from tables.', encoding='utf-8')
        topic = {'name': 'Relational databases and SQL joins with worked examples', 'concepts': ['INNER JOIN', 'LEFT JOIN', 'Relational algebra'], 'definitions': ['An inner join returns rows matching the specified condition.'], 'difficulty': 'foundational', 'prerequisites': ['Tables and keys'], 'source_pages': [1], 'queries': ['SQL joins introduction', 'SQL joins examples', 'SQL joins exam revision']}
        analysis = {'summary': 'Browser layout fixture. This isolated note checks long titles, study tabs, video cards, feedback controls and code wrapping without using live APIs.', 'topics': [topic], 'readability_warning': ''}
        app.db.execute('INSERT OR REPLACE INTO notes VALUES(?,?,?,?,?,?)', ('layout-check', 'Database Management Systems', 'Unit 1 / Relational databases', str(source), hashlib.sha256(source.read_bytes()).hexdigest(), json.dumps(analysis)))
        video = {'id': 'fixture', 'title': 'Understanding relational databases and SQL joins through a complete worked example', 'channelId': 'fixture', 'channelTitle': 'Layout preview teacher', 'duration_seconds': 900, 'views': 1000, 'role': 'solved problems', 'reason': 'A long explanation to verify that text fits comfortably within a video card on phones, tablets and desktop screens.', 'score': 8, 'confidence': 'medium', 'language': 'en', 'url': 'https://www.youtube.com/watch?v=fixture'}
        result = [{'topic': topic['name'], 'videos': [video], 'no_strong_match': False, 'estimated_minutes': 15, 'cache_hits': 1}]
        if not app.db.execute('SELECT 1 FROM history WHERE note=?', ('layout-check',)).fetchone():
            app.db.execute('INSERT INTO history(created,note,result) VALUES(?,?,?)', (1, 'layout-check', json.dumps(result)))
        app.db.commit()
        app.cache('aids:layout-check', [{'quiz': [{'question': 'Which join returns only matching rows?', 'options': ['INNER JOIN', 'LEFT JOIN'], 'answer': 'INNER JOIN', 'explanation': 'Both rows must match the join condition.'}], 'flashcards': [{'front': 'What is an inner join?', 'back': 'A join returning matching rows.'}], 'cheat_sheet': '### SQL joins\n\n```sql\nSELECT students.name, courses.title FROM students INNER JOIN courses ON students.course_id = courses.id;\n```'}], 1)
        print(folder)
    finally:
        app.close()


if __name__ == '__main__':
    seed()
