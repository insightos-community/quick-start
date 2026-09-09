#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2026 InsightOS
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Semantic workflow/失败实例 数据清理工具

清理 semantic.db 中失败的 workflow 及其关联数据, 以及 stopped/failed 的 Robot 实例。
默认 dry-run 只展示; --apply 才真正删除, 删除前自动备份。

用法:
    python3 cleanup_workflow.py                     # dry-run: 展示将清理的内容
    python3 cleanup_workflow.py --apply             # 执行清理 (自动备份)
    python3 cleanup_workflow.py --workflow wf-xxx   # 只清指定 workflow
    python3 cleanup_workflow.py --apply --include-chat   # 连同关联会话的 run_sessions 一起清
    python3 cleanup_workflow.py --db /path/to/semantic.db

保留 (默认不动):
    - status 为 ready/running 的 robot_runtime_instances
    - robot_pilots / chat_sessions / chat_messages / events / pilot_enrollments
    - 用户/项目/设置/技能等一切非 workflow 数据
"""

import argparse
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

DEFAULT_DB = "$HOME/workspace/semantic/semantic-framework/.output/data/semantic.db"
KEEP_INSTANCE_STATUS = ("ready", "running", "starting", "pending")


def qmarks(n):
    return ",".join("?" * n) if n else "NULL"


def fetch_ids(db, sql, args=()):
    return [r[0] for r in db.execute(sql, args)]


def count(db, table, where="1=1", args=()):
    return db.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", args).fetchone()[0]


def has_col(db, table, col):
    return col in [r[1] for r in db.execute(f"PRAGMA table_info({table})")]


def plan(db, args):
    """收集将删除的 (表, where, args, 描述) 列表"""
    ops = []
    if args.workflow:
        wf_ids = args.workflow
    else:
        wf_ids = fetch_ids(db, "SELECT id FROM workflows")
    convs = fetch_ids(
        db,
        f"SELECT DISTINCT conversation_id FROM workflows WHERE id IN ({qmarks(len(wf_ids))})"
        if wf_ids else "SELECT '' WHERE 0", wf_ids)

    task_ids = fetch_ids(
        db, f"SELECT id FROM tasks WHERE workflow_id IN ({qmarks(len(wf_ids))})" if wf_ids
        else "SELECT '' WHERE 0", wf_ids)

    if wf_ids:
        ops.append(("workflow_revisions", f"workflow_id IN ({qmarks(len(wf_ids))})", wf_ids,
                    f"{len(wf_ids)} 个 workflow 的修订"))
        if task_ids:
            ops.append(("task_dependencies", f"task_id IN ({qmarks(len(task_ids))})"
                        + " OR depends_on_task_id IN (" + qmarks(len(task_ids)) + ")",
                        task_ids + task_ids, f"{len(task_ids)} 个任务的依赖"))
            ops.append(("subtasks", f"task_id IN ({qmarks(len(task_ids))})", task_ids,
                        f"{len(task_ids)} 个任务的子任务"))
            sub_ids = fetch_ids(
                db, f"SELECT id FROM subtasks WHERE task_id IN ({qmarks(len(task_ids))})"
                if task_ids else "SELECT '' WHERE 0", task_ids)
            if sub_ids:
                ops.append(("subtask_dependencies",
                            f"subtask_id IN ({qmarks(len(sub_ids))})"
                            + " OR depends_on_subtask_id IN (" + qmarks(len(sub_ids)) + ")",
                            sub_ids + sub_ids, "子任务依赖"))
        ops.append(("run_sessions", f"workflow_id IN ({qmarks(len(wf_ids))})", wf_ids,
                    "workflow 的 run_sessions"))
        if convs and not args.keep_proposals:
            ops.append(("plan_proposals", f"conversation_id IN ({qmarks(len(convs))})", convs,
                        f"{len(convs)} 个会话的 plan_proposals"))
        ops.append(("tasks", f"workflow_id IN ({qmarks(len(wf_ids))})", wf_ids,
                    f"{len(wf_ids)} 个 workflow 的任务"))
        ops.append(("workflows", f"id IN ({qmarks(len(wf_ids))})", wf_ids,
                    f"{len(wf_ids)} 个 workflow"))
        if args.include_chat and convs:
            ops.append(("run_sessions", f"chat_session_id IN ({qmarks(len(convs))})", convs,
                        "关联会话的 run_sessions"))

    dead = fetch_ids(
        db,
        f"SELECT instance_id FROM robot_runtime_instances WHERE status NOT IN ({qmarks(len(KEEP_INSTANCE_STATUS))})",
        KEEP_INSTANCE_STATUS)
    if dead and args.dead_instances:
        for tbl, col in (("robot_runtime_port_leases", "instance_id"),
                         ("robot_executions", "request_key"),
                         ("robot_execution_events", "execution_id")):
            try:
                db.execute(f"SELECT 1 FROM {tbl} LIMIT 1")
            except sqlite3.OperationalError:
                continue
            if col == "request_key":
                # robot_executions 按 robot_id+subtask 关联, 无 instance 列; 死实例没有 executions 时自然为 0
                continue
            ops.append((tbl, f"{col} IN ({qmarks(len(dead))})", dead,
                        f"{len(dead)} 个失败/停止实例的 {tbl}"))
        ops.append(("robot_runtime_instances",
                    f"instance_id IN ({qmarks(len(dead))})", dead,
                    f"{len(dead)} 个失败/停止的 robot 实例"))
    if args.stale_enrollments:
        ops.append(("pilot_enrollments", "status = 'claimed'", (),
                    "已占用的 pilot 注册码"))
    return ops


def main():
    ap = argparse.ArgumentParser(description="清理 semantic.db 中失败的 workflow 数据")
    ap.add_argument("--db", default=DEFAULT_DB, help=f"数据库路径 (默认 {DEFAULT_DB})")
    ap.add_argument("--apply", action="store_true", help="真正执行删除 (默认 dry-run)")
    ap.add_argument("--workflow", action="append", default=[], help="指定 workflow id (可多次)")
    ap.add_argument("--keep-proposals", action="store_true", help="保留 plan_proposals")
    ap.add_argument("--no-dead-instances", dest="dead_instances", action="store_false",
                    help="不清理 failed/stopped 的 robot 实例")
    ap.add_argument("--include-chat", action="store_true",
                    help="连同关联会话的 run_sessions 一起清 (聊天记录本身仍保留)")
    ap.add_argument("--stale-enrollments", action="store_true", help="顺带清 claimed 的注册码")
    ap.add_argument("--keep-backup", dest="backup", action="store_false",
                    help="apply 时不做备份 (不建议)")
    args = ap.parse_args()

    dbpath = Path(os.path.expandvars(os.path.expanduser(args.db)))
    if not dbpath.exists():
        print(f"数据库不存在: {dbpath}")
        return 1
    db = sqlite3.connect(str(dbpath), timeout=10)
    db.row_factory = sqlite3.Row

    alive = [dict(r) for r in db.execute(
        f"SELECT instance_id, status FROM robot_runtime_instances "
        f"WHERE status IN ({qmarks(len(KEEP_INSTANCE_STATUS))})", KEEP_INSTANCE_STATUS)]
    ops = plan(db, args)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] 数据库: {dbpath}")
    total = 0
    for tbl, where, wargs, desc in ops:
        n = count(db, tbl, where, wargs)
        if n:
            print(f"  将删除 {tbl:<28} {n:>4} 行  ({desc})")
            total += n
    if not total:
        print("  没有需要清理的数据")
    if alive:
        print("保留的活跃实例:", ", ".join(f"{a['instance_id'][:24]}…({a['status']})" for a in alive))
    if not args.apply:
        print("\n确认无误后加 --apply 执行")
        return 0

    if args.backup:
        bak = dbpath.with_name(dbpath.name + f".bak-{time.strftime('%Y%m%d-%H%M%S')}")
        src = sqlite3.connect(str(dbpath))
        dst = sqlite3.connect(str(bak))
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
        print(f"已备份: {bak}")

    deleted = 0
    try:
        db.execute("BEGIN IMMEDIATE")
        for tbl, where, wargs, _desc in ops:
            cur = db.execute(f"DELETE FROM {tbl} WHERE {where}", wargs)
            deleted += cur.rowcount
            if cur.rowcount:
                print(f"  已删除 {tbl}: {cur.rowcount} 行")
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"删除失败已回滚: {e}")
        return 1
    finally:
        db.close()
    print(f"完成: 共删除 {deleted} 行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
