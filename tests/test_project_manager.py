"""Tests for ProjectManager, GitOps, and related components."""

import os
import tempfile
import unittest

from agents.brain.project_manager import ProjectManager, Task, Feature, Idea, Project


class TestProjectManager(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "test_projects.db")
        self.pm = ProjectManager(db_path=self.db_path)

    def test_create_project(self):
        proj = self.pm.create_project("Test App", "A test application", "# Spec\n...")
        self.assertIsInstance(proj, Project)
        self.assertEqual(proj.name, "Test App")
        self.assertEqual(proj.status, "planning")

    def test_create_project_with_domain(self):
        proj = self.pm.create_project("ML Pipeline", "A pipeline", "# Spec", domain="ML")
        self.assertEqual(proj.domain, "ML")
        active = self.pm.get_active_project()
        self.assertEqual(active.domain, "ML")

    def test_get_active_project(self):
        self.assertIsNone(self.pm.get_active_project())
        proj = self.pm.create_project("Test", "desc", "spec")
        active = self.pm.get_active_project()
        self.assertIsNotNone(active)
        self.assertEqual(active.id, proj.id)

    def test_single_active_project_limit(self):
        self.pm.create_project("P1", "d1", "s1")
        with self.assertRaises(ValueError):
            self.pm.create_project("P2", "d2", "s2")

    def test_detect_project(self):
        self.assertTrue(self.pm.detect_project("I want to build a web app with authentication and database"))
        self.assertTrue(self.pm.detect_project("Let's create a tool that has multiple features"))
        self.assertFalse(self.pm.detect_project("hello"))
        self.assertFalse(self.pm.detect_project("what's the weather?"))

    def test_detect_idea(self):
        self.assertTrue(self.pm.detect_idea("we should build a recommendation engine"))
        self.assertTrue(self.pm.detect_idea("idea: a CLI tool for DNS lookups"))
        self.assertTrue(self.pm.detect_idea("what if we made a chatbot"))
        self.assertTrue(self.pm.detect_idea("maybe we could automate deployments"))
        self.assertFalse(self.pm.detect_idea("let's build this now"))
        self.assertFalse(self.pm.detect_idea("hello"))

    def test_detect_backlog_query(self):
        self.assertTrue(self.pm.detect_backlog_query("what's in my backlog?"))
        self.assertTrue(self.pm.detect_backlog_query("show ideas"))
        self.assertTrue(self.pm.detect_backlog_query("what ideas do I have"))
        self.assertFalse(self.pm.detect_backlog_query("build something"))

    # ─── Idea Backlog Tests ───────────────────────────────────────────

    def test_add_idea(self):
        idea = self.pm.add_idea("Chatbot", "A chatbot for support", domain="ML")
        self.assertIsInstance(idea, Idea)
        self.assertEqual(idea.title, "Chatbot")
        self.assertEqual(idea.domain, "ML")
        self.assertEqual(idea.status, "backlog")

    def test_list_ideas(self):
        self.pm.add_idea("Idea 1", "desc1", domain="ML")
        self.pm.add_idea("Idea 2", "desc2", domain="Web")
        self.pm.add_idea("Idea 3", "desc3", domain="ML")

        all_ideas = self.pm.list_ideas()
        self.assertEqual(len(all_ideas), 3)

        ml_ideas = self.pm.list_ideas(domain="ML")
        self.assertEqual(len(ml_ideas), 2)

        web_ideas = self.pm.list_ideas(domain="Web")
        self.assertEqual(len(web_ideas), 1)

    def test_promote_idea(self):
        idea = self.pm.add_idea("My App", "Build my app", domain="Web")
        project = self.pm.promote_idea(idea.id)
        self.assertIsInstance(project, Project)
        self.assertEqual(project.name, "My App")
        self.assertEqual(project.domain, "Web")

        # Idea should no longer be in backlog
        ideas = self.pm.list_ideas()
        self.assertEqual(len(ideas), 0)

    def test_archive_idea(self):
        idea = self.pm.add_idea("Old idea", "not needed")
        self.pm.archive_idea(idea.id)
        ideas = self.pm.list_ideas()
        self.assertEqual(len(ideas), 0)

    def test_backlog_summary_empty(self):
        summary = self.pm.get_backlog_summary()
        self.assertIn("empty", summary.lower())

    def test_backlog_summary_with_ideas(self):
        self.pm.add_idea("Idea A", "desc a", domain="ML")
        self.pm.add_idea("Idea B", "desc b")
        summary = self.pm.get_backlog_summary()
        self.assertIn("Idea A", summary)
        self.assertIn("[ML]", summary)
        self.assertIn("Idea B", summary)
        self.assertIn("2 idea(s)", summary)

    # ─── Feature Hierarchy Tests ──────────────────────────────────────

    def test_add_and_get_features(self):
        proj = self.pm.create_project("Test", "desc", "spec")
        features = [
            Feature(id="f1", project_id=proj.id, title="Auth", description="Authentication", order=0),
            Feature(id="f2", project_id=proj.id, title="Upload", description="File upload", order=1),
        ]
        self.pm.add_features(proj.id, features)
        result = self.pm.get_features(proj.id)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].title, "Auth")
        self.assertEqual(result[1].title, "Upload")

    def test_feature_task_hierarchy(self):
        proj = self.pm.create_project("Test", "desc", "spec")
        features = [
            Feature(id="f1", project_id=proj.id, title="Auth", description="Auth feature", order=0),
            Feature(id="f2", project_id=proj.id, title="Upload", description="Upload feature", order=1),
        ]
        self.pm.add_features(proj.id, features)

        tasks = [
            Task(id="t1", feature_id="f1", project_id=proj.id, title="Design Auth", description="d", agent="builder", order=1),
            Task(id="t2", feature_id="f1", project_id=proj.id, title="Build Auth", description="d", agent="builder", depends_on=["t1"], order=2),
            Task(id="t3", feature_id="f2", project_id=proj.id, title="Build Upload", description="d", agent="builder", order=3),
        ]
        self.pm.decompose_into_tasks(proj.id, tasks)

        all_tasks = self.pm.get_all_tasks(proj.id)
        self.assertEqual(len(all_tasks), 3)
        self.assertEqual(all_tasks[0].feature_id, "f1")
        self.assertEqual(all_tasks[2].feature_id, "f2")

    def test_auto_complete_feature(self):
        proj = self.pm.create_project("Test", "desc", "spec")
        self.pm.add_features(proj.id, [
            Feature(id="f1", project_id=proj.id, title="Auth", description="", order=0),
        ])
        tasks = [
            Task(id="t1", feature_id="f1", project_id=proj.id, title="Task 1", description="d", agent="builder", order=1),
            Task(id="t2", feature_id="f1", project_id=proj.id, title="Task 2", description="d", agent="builder", depends_on=["t1"], order=2),
        ]
        self.pm.decompose_into_tasks(proj.id, tasks)

        self.pm.complete_task("t1", "done")
        feats = self.pm.get_features(proj.id)
        self.assertEqual(feats[0].status, "pending")  # not all done yet

        self.pm.complete_task("t2", "done")
        feats = self.pm.get_features(proj.id)
        self.assertEqual(feats[0].status, "completed")

    def test_set_task_in_progress_updates_feature(self):
        proj = self.pm.create_project("Test", "desc", "spec")
        self.pm.add_features(proj.id, [
            Feature(id="f1", project_id=proj.id, title="Auth", description="", order=0),
        ])
        tasks = [
            Task(id="t1", feature_id="f1", project_id=proj.id, title="Task 1", description="d", agent="builder", order=1),
        ]
        self.pm.decompose_into_tasks(proj.id, tasks)

        self.pm.set_task_in_progress("t1")
        feats = self.pm.get_features(proj.id)
        self.assertEqual(feats[0].status, "in_progress")

    # ─── Full Status Tests ────────────────────────────────────────────

    def test_get_full_status(self):
        proj = self.pm.create_project("Training Pipeline API", "desc", "spec", domain="ML")
        self.pm.add_features(proj.id, [
            Feature(id="f1", project_id=proj.id, title="Auth", description="", order=0),
            Feature(id="f2", project_id=proj.id, title="Upload", description="", order=1),
        ])
        tasks = [
            Task(id="t1", feature_id="f1", project_id=proj.id, title="Build auth", description="d", agent="builder", order=1),
            Task(id="t2", feature_id="f1", project_id=proj.id, title="Test auth", description="d", agent="verifier", depends_on=["t1"], order=2),
            Task(id="t3", feature_id="f2", project_id=proj.id, title="Build upload", description="d", agent="builder", order=3),
        ]
        self.pm.decompose_into_tasks(proj.id, tasks)

        # Complete all auth tasks
        self.pm.complete_task("t1", "done")
        self.pm.complete_task("t2", "done")

        full = self.pm.get_full_status(proj.id)
        self.assertEqual(full["name"], "Training Pipeline API")
        self.assertEqual(full["domain"], "ML")
        self.assertEqual(full["progress"], "1/2 features done")
        self.assertEqual(len(full["features"]), 2)

        auth_feat = full["features"][0]
        self.assertEqual(auth_feat["name"], "Auth")
        self.assertEqual(auth_feat["status"], "completed")
        self.assertEqual(auth_feat["tasks"], "2/2")

        upload_feat = full["features"][1]
        self.assertEqual(upload_feat["name"], "Upload")
        self.assertEqual(upload_feat["tasks"], "0/1")
        self.assertIn("current_task", upload_feat)

    # ─── Legacy Compat Tests ─────────────────────────────────────────

    def test_decompose_and_complete_tasks(self):
        proj = self.pm.create_project("Test", "desc", "spec")
        tasks = [
            Task(id="t1", feature_id="", project_id=proj.id, title="Design", description="Design DB", agent="builder", depends_on=[], order=1),
            Task(id="t2", feature_id="", project_id=proj.id, title="Build", description="Build API", agent="builder", depends_on=["t1"], order=2),
            Task(id="t3", feature_id="", project_id=proj.id, title="Test", description="Test it", agent="verifier", depends_on=["t2"], order=3),
        ]
        self.pm.decompose_into_tasks(proj.id, tasks)

        active = self.pm.get_active_project()
        self.assertEqual(active.status, "in_progress")

        next_t = self.pm.get_next_task(proj.id)
        self.assertEqual(next_t.id, "t1")

        self.pm.complete_task("t1", "Done designing")
        next_t = self.pm.get_next_task(proj.id)
        self.assertEqual(next_t.id, "t2")

        self.pm.complete_task("t2", "API built")
        next_t = self.pm.get_next_task(proj.id)
        self.assertEqual(next_t.id, "t3")

        self.pm.complete_task("t3", "All tests pass")
        active = self.pm.get_active_project()
        self.assertIsNone(active)

    def test_get_status(self):
        proj = self.pm.create_project("Test", "desc", "spec")
        tasks = [
            Task(id="t1", feature_id="", project_id=proj.id, title="Task 1", description="d", agent="builder", order=1),
            Task(id="t2", feature_id="", project_id=proj.id, title="Task 2", description="d", agent="builder", depends_on=["t1"], order=2),
        ]
        self.pm.decompose_into_tasks(proj.id, tasks)

        status = self.pm.get_status(proj.id)
        self.assertEqual(status.total_tasks, 2)
        self.assertEqual(status.completed_tasks, 0)

        self.pm.complete_task("t1", "done")
        status = self.pm.get_status(proj.id)
        self.assertEqual(status.completed_tasks, 1)
        self.assertAlmostEqual(status.progress_pct, 50.0)

    def test_pause_and_resume(self):
        proj = self.pm.create_project("Test", "desc", "spec")
        self.pm.update_project_status(proj.id, "paused")
        self.assertIsNone(self.pm.get_active_project())

        proj2 = self.pm.create_project("P2", "d2", "s2")
        self.assertIsNotNone(proj2)


class TestGitOps(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        from agents.common.gitops import GitOps
        self.gitops = GitOps(self.tmp)

    def test_init_repo(self):
        self.assertTrue(self.gitops.init_repo())
        self.assertTrue(os.path.exists(os.path.join(self.tmp, ".git")))
        self.assertTrue(self.gitops.init_repo())

    def test_auto_commit(self):
        self.gitops.init_repo()
        os.system(f'cd {self.tmp} && git config user.email "test@test.com" && git config user.name "Test"')
        with open(os.path.join(self.tmp, "test.py"), "w") as f:
            f.write("print('hello')\n")
        commit_hash = self.gitops.auto_commit("Initial test commit")
        self.assertIsNotNone(commit_hash)
        self.assertTrue(len(commit_hash) > 0)

    def test_auto_commit_nothing(self):
        self.gitops.init_repo()
        os.system(f'cd {self.tmp} && git config user.email "test@test.com" && git config user.name "Test"')
        with open(os.path.join(self.tmp, "init.txt"), "w") as f:
            f.write("init")
        self.gitops.auto_commit("init")
        result = self.gitops.auto_commit("Empty commit")
        self.assertIsNone(result)

    def test_pre_commit_check_secrets(self):
        self.gitops.init_repo()
        os.system(f'cd {self.tmp} && git config user.email "test@test.com" && git config user.name "Test"')
        with open(os.path.join(self.tmp, "config.py"), "w") as f:
            f.write('API_KEY = "sk-abcdefghijklmnopqrstuvwxyz1234567890"\n')
        os.system(f'cd {self.tmp} && git add config.py')
        warnings = self.gitops.pre_commit_check()
        self.assertTrue(len(warnings) > 0)
        self.assertTrue(any("OpenAI" in w or "secret" in w.lower() for w in warnings))

    def test_pre_commit_check_env_file(self):
        self.gitops.init_repo()
        os.system(f'cd {self.tmp} && git config user.email "test@test.com" && git config user.name "Test"')
        with open(os.path.join(self.tmp, ".env"), "w") as f:
            f.write("SECRET=foo\n")
        os.system(f'cd {self.tmp} && git add -f .env')
        warnings = self.gitops.pre_commit_check()
        self.assertTrue(any(".env" in w for w in warnings))

    def test_get_status(self):
        self.gitops.init_repo()
        status = self.gitops.get_status()
        self.assertIn("branch", status)

    def test_get_log(self):
        self.gitops.init_repo()
        os.system(f'cd {self.tmp} && git config user.email "test@test.com" && git config user.name "Test"')
        with open(os.path.join(self.tmp, "f.txt"), "w") as f:
            f.write("x")
        self.gitops.auto_commit("test log")
        log = self.gitops.get_log()
        self.assertTrue(len(log) > 0)
        self.assertEqual(log[0]["message"], "test log")

    def test_rollback(self):
        self.gitops.init_repo()
        os.system(f'cd {self.tmp} && git config user.email "test@test.com" && git config user.name "Test"')
        with open(os.path.join(self.tmp, "a.txt"), "w") as f:
            f.write("v1")
        self.gitops.auto_commit("v1")
        with open(os.path.join(self.tmp, "a.txt"), "w") as f:
            f.write("v2")
        self.gitops.auto_commit("v2")
        self.assertTrue(self.gitops.rollback())


if __name__ == "__main__":
    unittest.main()
