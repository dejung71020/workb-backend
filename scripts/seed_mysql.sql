-- Seed dummy data for meeting_assistant (MySQL 8.0)
-- Safe to re-run: it clears existing rows in dependent-first order.

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- Clear tables (child -> parent)
DELETE FROM minute_photos;
DELETE FROM review_requests;
DELETE FROM meeting_minutes;
DELETE FROM decisions;

DELETE FROM agenda_items;
DELETE FROM agendas;
DELETE FROM meeting_participants;

DELETE FROM action_items;
DELETE FROM wbs_tasks;
DELETE FROM wbs_epics;
DELETE FROM reports;

DELETE FROM integrations;
DELETE FROM speaker_profiles;
DELETE FROM meetings;

DELETE FROM device_settings;
DELETE FROM invite_codes;
DELETE FROM workspace_members;
DELETE FROM workspaces;
DELETE FROM users;

SET FOREIGN_KEY_CHECKS = 1;

-- -------------------------------------------------------------------
-- users (5)
-- -------------------------------------------------------------------
INSERT INTO users (id, email, password_hash, name, social_provider, social_id, created_at, updated_at) VALUES
  (1, 'user1@example.com', NULL, 'User One',   'none',  NULL, NOW(), NOW()),
  (2, 'user2@example.com', NULL, 'User Two',   'google','google-2', NOW(), NOW()),
  (3, 'user3@example.com', NULL, 'User Three', 'kakao', 'kakao-3',  NOW(), NOW()),
  (4, 'user4@example.com', NULL, 'User Four',  'none',  NULL, NOW(), NOW()),
  (5, 'user5@example.com', NULL, 'User Five',  'google','google-5', NOW(), NOW());

-- -------------------------------------------------------------------
-- workspaces (5)
-- -------------------------------------------------------------------
INSERT INTO workspaces (id, owner_id, name, industry, default_language, summary_style, logo_url, created_at, updated_at) VALUES
  (1, 1, 'Workspace A', 'SaaS',     'ko', 'bullet', NULL, NOW(), NOW()),
  (2, 2, 'Workspace B', 'Finance',  'en', 'short',  NULL, NOW(), NOW()),
  (3, 3, 'Workspace C', 'Retail',   'ko', 'detail', NULL, NOW(), NOW()),
  (4, 4, 'Workspace D', 'Media',    'en', 'bullet', NULL, NOW(), NOW()),
  (5, 5, 'Workspace E', 'R&D',      'ko', 'short',  NULL, NOW(), NOW());

-- -------------------------------------------------------------------
-- workspace_members (5)
-- -------------------------------------------------------------------
INSERT INTO workspace_members (id, workspace_id, user_id, role, joined_at) VALUES
  (1, 1, 1, 'admin',  NOW()),
  (2, 2, 2, 'admin',  NOW()),
  (3, 3, 3, 'admin',  NOW()),
  (4, 4, 4, 'admin',  NOW()),
  (5, 5, 5, 'admin',  NOW());

-- -------------------------------------------------------------------
-- device_settings (5)  (workspace_id is UNIQUE)
-- -------------------------------------------------------------------
INSERT INTO device_settings (id, workspace_id, device_name, microphone_device, webcam_device, webcam_enabled, updated_at) VALUES
  (1, 1, 'Office PC A', 'Microphone A', 'Webcam A', 1, NOW()),
  (2, 2, 'Office PC B', 'Microphone B', 'Webcam B', 0, NOW()),
  (3, 3, 'Office PC C', 'Microphone C', 'Webcam C', 1, NOW()),
  (4, 4, 'Office PC D', NULL,           'Webcam D', 0, NOW()),
  (5, 5, 'Office PC E', 'Microphone E', 'Webcam E', 1, NOW());

-- -------------------------------------------------------------------
-- invite_codes (5)  (code is UNIQUE)
-- -------------------------------------------------------------------
INSERT INTO invite_codes (id, workspace_id, code, role, is_used, used_by, expires_at, created_at) VALUES
  (1, 1, 'INV-A-001', 'member', 0, NULL, DATE_ADD(NOW(), INTERVAL 30 DAY), NOW()),
  (2, 2, 'INV-B-001', 'viewer', 0, NULL, DATE_ADD(NOW(), INTERVAL 30 DAY), NOW()),
  (3, 3, 'INV-C-001', 'member', 1, 4,    DATE_ADD(NOW(), INTERVAL 30 DAY), NOW()),
  (4, 4, 'INV-D-001', 'viewer', 1, 5,    DATE_ADD(NOW(), INTERVAL 30 DAY), NOW()),
  (5, 5, 'INV-E-001', 'member', 0, NULL, DATE_ADD(NOW(), INTERVAL 30 DAY), NOW());

-- -------------------------------------------------------------------
-- integrations (5)
-- -------------------------------------------------------------------
INSERT INTO integrations (id, workspace_id, service, access_token, refresh_token, token_expires_at, extra_config, is_connected, updated_at) VALUES
  (1, 1, 'slack',          NULL, NULL, NULL, JSON_OBJECT('channel','C123'), 0, NOW()),
  (2, 2, 'jira',           NULL, NULL, NULL, JSON_OBJECT('projectKey','WB'), 0, NOW()),
  (3, 3, 'notion',         NULL, NULL, NULL, JSON_OBJECT('db','dummy'), 0, NOW()),
  (4, 4, 'google_calendar',NULL, NULL, NULL, JSON_OBJECT('calendarId','primary'), 0, NOW()),
  (5, 5, 'kakao',          NULL, NULL, NULL, JSON_OBJECT('scope','basic'), 0, NOW());

-- -------------------------------------------------------------------
-- meetings (5)
-- -------------------------------------------------------------------
INSERT INTO meetings (id, workspace_id, created_by, title, meeting_type, status, scheduled_at, started_at, ended_at, google_calendar_event_id, created_at, updated_at) VALUES
  (1, 1, 1, 'Kickoff Meeting',        'kickoff',   'scheduled',  DATE_ADD(NOW(), INTERVAL 1 DAY),  NULL, NULL, NULL, NOW(), NOW()),
  (2, 2, 2, 'Weekly Sync',            'weekly',    'in_progress',DATE_SUB(NOW(), INTERVAL 1 HOUR), DATE_SUB(NOW(), INTERVAL 50 MINUTE), NULL, NULL, NOW(), NOW()),
  (3, 3, 3, 'Product Review',         'review',    'done',       DATE_SUB(NOW(), INTERVAL 7 DAY),  DATE_SUB(NOW(), INTERVAL 7 DAY),  DATE_SUB(NOW(), INTERVAL 7 DAY) + INTERVAL 1 HOUR, NULL, NOW(), NOW()),
  (4, 4, 4, 'Customer Feedback',      'feedback',  'scheduled',  DATE_ADD(NOW(), INTERVAL 3 DAY),  NULL, NULL, NULL, NOW(), NOW()),
  (5, 5, 5, 'Engineering Retrospect', 'retro',     'done',       DATE_SUB(NOW(), INTERVAL 14 DAY), DATE_SUB(NOW(), INTERVAL 14 DAY), DATE_SUB(NOW(), INTERVAL 14 DAY) + INTERVAL 45 MINUTE, NULL, NOW(), NOW());

-- -------------------------------------------------------------------
-- meeting_participants (5)
-- -------------------------------------------------------------------
INSERT INTO meeting_participants (id, meeting_id, user_id, speaker_label, is_host) VALUES
  (1, 1, 1, 'SPEAKER_01', 1),
  (2, 2, 2, 'SPEAKER_01', 1),
  (3, 3, 3, 'SPEAKER_01', 1),
  (4, 4, 4, 'SPEAKER_01', 1),
  (5, 5, 5, 'SPEAKER_01', 1);

-- -------------------------------------------------------------------
-- agendas (5)
-- -------------------------------------------------------------------
INSERT INTO agendas (id, meeting_id, created_by, created_at) VALUES
  (1, 1, 1, NOW()),
  (2, 2, 2, NOW()),
  (3, 3, 3, NOW()),
  (4, 4, 4, NOW()),
  (5, 5, 5, NOW());

-- -------------------------------------------------------------------
-- agenda_items (5)
-- -------------------------------------------------------------------
INSERT INTO agenda_items (id, agenda_id, title, presenter_id, estimated_minutes, reference_url, order_index) VALUES
  (1, 1, 'Intro & goals',          1, 10, NULL, 1),
  (2, 2, 'Status updates',         2, 15, NULL, 1),
  (3, 3, 'Feature review',         3, 20, 'https://example.com/spec', 1),
  (4, 4, 'Feedback highlights',    4, 15, NULL, 1),
  (5, 5, 'Retro: what to improve', 5, 20, NULL, 1);

-- -------------------------------------------------------------------
-- speaker_profiles (5)
-- -------------------------------------------------------------------
INSERT INTO speaker_profiles (id, user_id, workspace_id, voice_model_path, diarization_method, is_verified, created_at, updated_at) VALUES
  (1, 1, 1, NULL, 'stereo',      1, NOW(), NOW()),
  (2, 2, 2, NULL, 'diarization', 0, NOW(), NOW()),
  (3, 3, 3, NULL, 'stereo',      0, NOW(), NOW()),
  (4, 4, 4, NULL, 'diarization', 1, NOW(), NOW()),
  (5, 5, 5, NULL, 'stereo',      0, NOW(), NOW());

-- -------------------------------------------------------------------
-- decisions (5)
-- -------------------------------------------------------------------
INSERT INTO decisions (id, meeting_id, content, speaker_id, detected_at, is_confirmed) VALUES
  (1, 1, 'Decide project scope v1', 1, NOW(), 0),
  (2, 2, 'Adopt weekly reporting',  2, NOW(), 1),
  (3, 3, 'Ship MVP by end of month',3, NOW(), 1),
  (4, 4, 'Collect NPS monthly',     4, NOW(), 0),
  (5, 5, 'Refactor auth module',    5, NOW(), 1);

-- -------------------------------------------------------------------
-- meeting_minutes (5)  (meeting_id is UNIQUE)
-- -------------------------------------------------------------------
INSERT INTO meeting_minutes (id, meeting_id, content, summary, status, reviewer_id, review_status, created_at, updated_at) VALUES
  (1, 1, 'Minutes for meeting #1', 'Summary #1', 'draft',   NULL, NULL,       NOW(), NOW()),
  (2, 2, 'Minutes for meeting #2', 'Summary #2', 'editing', 1,    'pending',  NOW(), NOW()),
  (3, 3, 'Minutes for meeting #3', 'Summary #3', 'final',   2,    'approved', NOW(), NOW()),
  (4, 4, 'Minutes for meeting #4', 'Summary #4', 'draft',   NULL, NULL,       NOW(), NOW()),
  (5, 5, 'Minutes for meeting #5', 'Summary #5', 'final',   3,    'approved', NOW(), NOW());

-- -------------------------------------------------------------------
-- minute_photos (5)
-- -------------------------------------------------------------------
INSERT INTO minute_photos (id, minute_id, photo_url, taken_at, taken_by) VALUES
  (1, 1, 'https://example.com/photo1.jpg', NOW(), 1),
  (2, 2, 'https://example.com/photo2.jpg', NOW(), 2),
  (3, 3, 'https://example.com/photo3.jpg', NOW(), 3),
  (4, 4, 'https://example.com/photo4.jpg', NOW(), 4),
  (5, 5, 'https://example.com/photo5.jpg', NOW(), 5);

-- -------------------------------------------------------------------
-- review_requests (5)
-- -------------------------------------------------------------------
INSERT INTO review_requests (id, minute_id, requester_id, reviewer_id, notify_slack, notify_kakao, status, requested_at, reviewed_at) VALUES
  (1, 1, 1, 2, 1, 0, 'pending',  NOW(), NULL),
  (2, 2, 2, 3, 1, 0, 'pending',  NOW(), NULL),
  (3, 3, 3, 4, 0, 1, 'approved', NOW(), NOW()),
  (4, 4, 4, 5, 0, 1, 'rejected', NOW(), NOW()),
  (5, 5, 5, 1, 1, 1, 'pending',  NOW(), NULL);

-- -------------------------------------------------------------------
-- action_items (5)
-- -------------------------------------------------------------------
INSERT INTO action_items (id, meeting_id, content, assignee_id, due_date, status, detected_at, jira_issue_id) VALUES
  (1, 1, 'Create initial project plan', 2, DATE_ADD(CURDATE(), INTERVAL 7 DAY),  'pending',     NOW(), NULL),
  (2, 2, 'Share weekly KPI dashboard',  3, DATE_ADD(CURDATE(), INTERVAL 3 DAY),  'in_progress', NOW(), NULL),
  (3, 3, 'Prepare release checklist',   4, DATE_ADD(CURDATE(), INTERVAL 10 DAY), 'pending',     NOW(), NULL),
  (4, 4, 'Summarize customer feedback', 5, DATE_ADD(CURDATE(), INTERVAL 5 DAY),  'done',        NOW(), NULL),
  (5, 5, 'Refactor login flow',         1, DATE_ADD(CURDATE(), INTERVAL 14 DAY), 'in_progress', NOW(), NULL);

-- -------------------------------------------------------------------
-- wbs_epics (5)
-- -------------------------------------------------------------------
INSERT INTO wbs_epics (id, meeting_id, title, order_index, jira_epic_id) VALUES
  (1, 1, 'Planning',     1, NULL),
  (2, 2, 'Execution',    1, NULL),
  (3, 3, 'QA & Release', 1, NULL),
  (4, 4, 'Growth',       1, NULL),
  (5, 5, 'Tech Debt',    1, NULL);

-- -------------------------------------------------------------------
-- wbs_tasks (5)
-- -------------------------------------------------------------------
INSERT INTO wbs_tasks (id, epic_id, title, assignee_id, priority, due_date, progress, status, jira_issue_id, notion_page_id, created_at, updated_at) VALUES
  (1, 1, 'Define requirements', 1, 'high',    DATE_ADD(CURDATE(), INTERVAL 5 DAY),  20, 'in_progress', NULL, NULL, NOW(), NOW()),
  (2, 2, 'Implement API v1',    2, 'medium',  DATE_ADD(CURDATE(), INTERVAL 10 DAY), 40, 'in_progress', NULL, NULL, NOW(), NOW()),
  (3, 3, 'Write test cases',    3, 'medium',  DATE_ADD(CURDATE(), INTERVAL 12 DAY), 10, 'todo',        NULL, NULL, NOW(), NOW()),
  (4, 4, 'Analyze churn',       4, 'low',     DATE_ADD(CURDATE(), INTERVAL 20 DAY),  0, 'todo',        NULL, NULL, NOW(), NOW()),
  (5, 5, 'Refactor DB layer',   5, 'critical',DATE_ADD(CURDATE(), INTERVAL 15 DAY), 60, 'in_progress', NULL, NULL, NOW(), NOW());

-- -------------------------------------------------------------------
-- reports (5)
-- -------------------------------------------------------------------
INSERT INTO reports (id, meeting_id, created_by, format, file_url, created_at) VALUES
  (1, 1, 1, 'html', NULL, NOW()),
  (2, 2, 2, 'pptx', NULL, NOW()),
  (3, 3, 3, 'xlsx', NULL, NOW()),
  (4, 4, 4, 'html', NULL, NOW()),
  (5, 5, 5, 'pptx', NULL, NOW());

