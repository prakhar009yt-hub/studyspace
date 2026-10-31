import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from muj_study.core import App, private_write
from muj_study.study_export import build_study_export, export_study_to_file, FORMAT


class StudyExportTests(unittest.TestCase):
    def test_export_structure_and_lab_exclusion(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            with patch.dict(os.environ, {
                'MUJ_DATA_DIR': str(base / 'data'),
                'MUJ_CONFIG': str(base / 'config.json'),
                'MUJ_PRIVATE_DIR': str(base / 'private')
            }):
                app = App()
                app.save_config()

                # Insert courses: one theory, one lab
                app.db.execute("INSERT INTO courses VALUES ('https://mujlms.manipal.edu/d2l/home/1', 'Data Structures', '1', 1, 3)")
                app.db.execute("INSERT INTO courses VALUES ('https://mujlms.manipal.edu/d2l/home/2', 'Data Structures Lab', '2', 1, 3)")

                # Insert notes: one theory, one lab
                analysis_theory = {
                    'summary': 'Binary search trees and AVL trees.',
                    'readability_warning': '',
                    'topics': [{
                        'name': 'Binary Search Trees',
                        'concepts': ['Insertion', 'Deletion', 'Search'],
                        'definitions': ['A binary search tree has left subtree < root < right subtree.'],
                        'prerequisites': ['Binary trees'],
                        'difficulty': 'intermediate',
                        'source_pages': [1, 2]
                    }]
                }
                analysis_lab = {
                    'summary': 'Lab experiments',
                    'topics': [{'name': 'Lab task'}]
                }

                note1_id = 'note-theory-1'
                note2_id = 'note-lab-1'
                dummy_hash = 'a' * 64
                app.db.execute("INSERT INTO notes VALUES (?,?,?,?,?,?)",
                               (note1_id, 'Data Structures', 'Unit 1', str(base / 'note1.pdf'), dummy_hash, json.dumps(analysis_theory)))
                app.db.execute("INSERT INTO notes VALUES (?,?,?,?,?,?)",
                               (note2_id, 'Data Structures Lab', 'Unit 1', str(base / 'note2.pdf'), dummy_hash, json.dumps(analysis_lab)))
                
                app.db.execute("INSERT INTO note_semesters VALUES (?, 3)", (note1_id,))
                app.db.execute("INSERT INTO note_semesters VALUES (?, 3)", (note2_id,))

                # Set topic state (weak=1, covered=0)
                app.db.execute("INSERT INTO topics VALUES ('binary search trees', 1, 0, 100.0)")

                # Add cached quiz/flashcard
                app.cache('aids:' + note1_id, [{
                    'quiz': [{
                        'question': 'What is the time complexity of searching a balanced BST?',
                        'answer': 'O(log n)',
                        'explanation': 'Height of balanced BST is log n.',
                        'options': ['O(1)', 'O(log n)', 'O(n)']
                    }],
                    'flashcards': [{
                        'front': 'BST property',
                        'back': 'Left < Root < Right'
                    }]
                }], 30)

                # Add recommended video in history
                history_result = [{
                    'topic': 'Binary Search Trees',
                    'videos': [{
                        'id': 'abcdefghijk',
                        'title': 'BST Complete Guide',
                        'channelTitle': 'CS Professor',
                        'reason': 'Clear diagrams and code walkthrough',
                        'score': 9.2,
                        'views': 45000
                    }]
                }]
                app.db.execute("INSERT INTO history (created, note, result) VALUES (?, ?, ?)",
                               (1000.0, note1_id, json.dumps(history_result)))
                app.db.commit()

                export_data = build_study_export(app, semester=3)
                self.assertEqual(export_data['format'], FORMAT)
                self.assertEqual(export_data['semester'], 3)
                
                # Check lab exclusion
                course_names = [c['name'] for c in export_data['courses']]
                self.assertIn('Data Structures', course_names)
                self.assertNotIn('Data Structures Lab', course_names)

                note_titles = [n['course'] for n in export_data['notes']]
                self.assertIn('Data Structures', note_titles)
                self.assertNotIn('Data Structures Lab', note_titles)
                self.assertEqual(len(export_data['notes']), 1)

                exported_note = export_data['notes'][0]
                self.assertEqual(exported_note['id'], note1_id)
                self.assertEqual(exported_note['title'], 'note1.pdf')
                self.assertEqual(exported_note['hash'], dummy_hash)

                # Check analysis contents
                note_analysis = exported_note['analysis']
                self.assertEqual(note_analysis['summary'], 'Binary search trees and AVL trees.')
                self.assertEqual(len(note_analysis['topics']), 1)
                
                topic_data = note_analysis['topics'][0]
                self.assertEqual(topic_data['name'], 'Binary Search Trees')
                self.assertEqual(topic_data['difficulty'], 'intermediate')
                self.assertEqual(len(topic_data['videos']), 1)
                self.assertEqual(topic_data['videos'][0]['id'], 'abcdefghijk')
                self.assertEqual(topic_data['videos'][0]['channel'], 'CS Professor')

                # Check quiz and flashcards
                self.assertEqual(len(note_analysis['quiz']), 1)
                self.assertEqual(note_analysis['quiz'][0]['answer'], 'O(log n)')
                self.assertEqual(len(note_analysis['flashcards']), 1)
                self.assertEqual(note_analysis['flashcards'][0]['front'], 'BST property')

                # Check progress
                progress_key = f"{note1_id}:binary search trees"
                self.assertIn(progress_key, export_data['progress'])
                self.assertTrue(export_data['progress'][progress_key]['weak'])
                self.assertFalse(export_data['progress'][progress_key]['covered'])

                # Test file write
                dest = export_study_to_file(app, semester=3)
                self.assertTrue(dest.exists())
                loaded = json.loads(dest.read_text(encoding='utf-8'))
                self.assertEqual(loaded['format'], FORMAT)
                self.assertEqual(len(loaded['notes']), 1)

                app.close()

