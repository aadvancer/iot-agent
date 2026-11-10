"""Streamlit dashboard for synthetic cases and saved diagnosis runs."""
import json
from pathlib import Path

import streamlit as st
import yaml
from openai import OpenAIError

from eval.metrics import calculate_metrics


ROOT = Path(__file__).resolve().parent
CASES_DIR = ROOT / "data" / "cases"
RESULTS_DIR = ROOT / "results" / "raw"
TAXONOMY_PATH = ROOT / "data" / "taxonomy.yaml"
HAND_AUTHORED = {"C001", "C002", "C003", "C004", "C005"}


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _load_cases():
    return {
        path.stem: _read_json(path)
        for path in sorted(CASES_DIR.glob("C*.json"))
    }


def _load_results():
    results = {}
    if not RESULTS_DIR.exists():
        return results
    for system_dir in sorted(path for path in RESULTS_DIR.iterdir() if path.is_dir()):
        rows = []
        for path in sorted(system_dir.glob("C*.json")):
            row = _read_json(path)
            if "pred_root_cause" in row and "gt_root_cause" in row:
                rows.append(row)
        if rows:
            results[system_dir.name] = rows
    return results


def _render_metrics(results):
    if not results:
        st.info("尚无评估结果。先运行 `python -m eval.run_cases --system topology`，然后刷新页面。")
        return

    metric_rows = {}
    for system, rows in results.items():
        metrics = calculate_metrics(rows)
        metric_rows[system] = {
            "案例数": metrics["case_count"],
            "根因诊断成功率": metrics["diagnosis_success_rate"],
            "L1/L2 分类准确率": metrics["fault_classification_accuracy"],
            "平均客户交互轮数（经一线转达）": metrics["average_interaction_rounds"],
            "重复询问率": metrics["redundant_inquiry_rate"],
            "可用性评分": metrics["support_usability_score"],
        }

    st.subheader("系统评估对比")
    st.dataframe(
        [{"系统": system, **values} for system, values in metric_rows.items()],
        use_container_width=True,
    )
    chart_metrics = [
        {
            "系统": system,
            "根因诊断成功率": values["根因诊断成功率"],
            "L1/L2 分类准确率": values["L1/L2 分类准确率"],
        }
        for system, values in metric_rows.items()
    ]
    st.bar_chart(chart_metrics, x="系统", y=["根因诊断成功率", "L1/L2 分类准确率"])

    counts = [
        {
            "系统": system,
            "正确": sum(row["pred_root_cause"] == row["gt_root_cause"] for row in rows),
            "错误": sum(row["pred_root_cause"] != row["gt_root_cause"] for row in rows),
        }
        for system, rows in results.items()
    ]
    st.subheader("根因诊断正确 / 错误数量")
    st.bar_chart(counts, x="系统", y=["正确", "错误"])

    st.subheader("逐案例结果")
    system = st.selectbox("评估系统", list(results))
    selected = results[system]
    st.dataframe(
        [
            {
                "案例": row["case_id"],
                "预测根因": row["pred_root_cause"],
                "真实根因": row["gt_root_cause"],
                "预测分流": row.get("pred_tier", "-"),
                "真实分流": row.get("gt_tier", "-"),
                "正确": row["pred_root_cause"] == row["gt_root_cause"],
            }
            for row in selected
        ],
        use_container_width=True,
    )


def _case_overview_rows(cases):
    rows = []
    for case_id, case in cases.items():
        devices = case["hidden_state"]["devices"]
        abnormal = [d["name"] for d in devices if d["status"] != "online"]
        rows.append({
            "案例": case_id,
            "来源": "手写" if case_id in HAND_AUTHORED else "模板生成",
            "客户投诉": case["complaint"],
            "真实根因": case["gt_root_cause"],
            "分流": case["gt_tier"],
            "难度": case.get("difficulty", ""),
            "关键检查阶段": ", ".join(case.get("gt_key_checks", [])),
            "设备数": len(devices),
            "异常设备": ", ".join(abnormal) or "无",
            "基站故障码": ", ".join(case["hidden_state"]["base_station"].get("error_codes", [])) or "无",
            "案例说明": case.get("notes", ""),
        })
    return rows


def _render_case_overview(cases):
    st.subheader(f"案例总览（共 {len(cases)} 个）")
    rows = _case_overview_rows(cases)
    col1, col2, col3, col4 = st.columns(4)
    tiers = col1.multiselect("分流", sorted({r["分流"] for r in rows}))
    causes = col2.multiselect("真实根因", sorted({r["真实根因"] for r in rows}))
    levels = col3.multiselect("难度", sorted({r["难度"] for r in rows}))
    sources = col4.multiselect("来源", sorted({r["来源"] for r in rows}))
    keyword = st.text_input("在投诉和说明中搜索")
    shown = [
        r for r in rows
        if (not tiers or r["分流"] in tiers)
        and (not causes or r["真实根因"] in causes)
        and (not levels or r["难度"] in levels)
        and (not sources or r["来源"] in sources)
        and (not keyword or keyword.lower() in (r["客户投诉"] + r["案例说明"]).lower())
    ]
    st.caption(f"显示 {len(shown)} / {len(rows)} 个案例。C001–C005 为手写，其余为脚本模板生成。")
    st.dataframe(
        shown,
        use_container_width=True,
        hide_index=True,
        height=min(900, 40 + 36 * max(len(shown), 1)),
        column_config={
            "客户投诉": st.column_config.TextColumn(width="large"),
            "案例说明": st.column_config.TextColumn(width="large"),
        },
    )
    st.write("**分布**")
    left, right = st.columns(2)
    left.bar_chart({k: sum(r["真实根因"] == k for r in rows) for k in sorted({r["真实根因"] for r in rows})})
    right.bar_chart({k: sum(r["分流"] == k for r in rows) for k in sorted({r["分流"] for r in rows})})
    st.caption("要查看某个案例的设备拓扑、日志和客户已知信息，请切换到“案例浏览”页。")


def _render_case_browser(cases, results, causes):
    case_ids = list(cases)
    selected_id = st.selectbox("选择案例", case_ids)
    case = cases[selected_id]
    state = case["hidden_state"]

    st.header(f"{selected_id} · {case['gt_root_cause']}")
    st.write(case["complaint"])
    col1, col2, col3 = st.columns(3)
    col1.metric("真实分流", case["gt_tier"])
    col2.metric("难度", case.get("difficulty", "未标注"))
    col3.metric("检查阶段", ", ".join(case.get("gt_key_checks", [])))
    with st.expander("根因标签说明"):
        st.write(causes.get(case["gt_root_cause"], {}).get("symptoms", []))
        st.write(causes.get(case["gt_root_cause"], {}).get("evidence", ""))
    with st.expander("基站状态"):
        st.json(state["base_station"])
    with st.expander("设备拓扑与设备状态", expanded=True):
        st.dataframe(state["devices"], use_container_width=True)
    with st.expander("设备日志"):
        st.code("\n".join(state["logs"]) or "无日志")
    with st.expander("用户已知信息"):
        st.json(case.get("user_knowledge", {}))
    with st.expander("模拟操作结果"):
        st.json(case.get("action_outcomes", {}))
    if case.get("notes"):
        st.caption(case["notes"])

    matching = {
        system: next((row for row in rows if row["case_id"] == selected_id), None)
        for system, rows in results.items()
    }
    matching = {system: row for system, row in matching.items() if row}
    st.subheader("已有诊断结果")
    if not matching:
        st.info("这个案例还没有保存的诊断结果。")
        return

    system = st.selectbox("结果系统", list(matching), key="case_result_system")
    result = matching[system]
    correct = result["pred_root_cause"] == case["gt_root_cause"]
    st.metric(
        "预测根因",
        result["pred_root_cause"],
        delta="正确" if correct else "与标准答案不符",
        delta_color="normal" if correct else "inverse",
    )
    st.write(f"**预测分流：** {result.get('pred_tier', '未记录')}")
    st.write(f"**诊断理由：** {result.get('rationale', '未记录')}")
    if not _is_ticket(result.get("output") or {}):
        _render_rules(result.get("triggers"))
    if result.get("output"):
        st.write("**一线处理建议 / 升级工单：**")
        _render_output(result["output"], result)
    if result.get("trace"):
        with st.expander("完整工具调用轨迹"):
            st.json(result["trace"])


RULE_NAMES = {
    "R1_BATCH": "R1 多设备同时异常（基站在线）",
    "R2_PROTOCOL": "R2 固件/协议不兼容且 OTA 无法解决",
    "R3_FIX_FAILED": "R3 标准一线修复已执行但无效",
    "R4_TOPOLOGY_MISMATCH": "R4 App 与基站绑定表不一致",
    "R5_HW_PERSISTS": "R5 复位后放在基站旁仍故障（疑似硬件）",
}
DEVICE_STATUS = {
    "online": "在线", "offline": "离线", "intermittent": "间歇掉线",
    "connected_no_events": "已连接但无事件", "not_paired": "未配对",
}


def _rule_lines(triggers):
    return [f"- **{RULE_NAMES.get(t.get('rule'), t.get('rule'))}**：{t.get('evidence', '')}" for t in triggers]


def _render_rules(triggers):
    if triggers:
        st.markdown("**触发的升级规则：**\n" + "\n".join(_rule_lines(triggers)))


def _fmt(value, unit=""):
    return "—" if value is None or value == "" else f"{value}{unit}"


def _ticket_markdown(output, result=None):
    """FAE escalation ticket as readable Markdown (shown on the page and offered for download)."""
    result = result or {}
    ticket = output.get("ticket") or {}
    lines = ["#### 🚨 FAE 升级工单", ""]
    meta = []
    if result.get("case_id"):
        meta.append(f"**工单号：** {result['case_id']}")
    if result.get("pred_root_cause"):
        meta.append(f"**诊断根因：** `{result['pred_root_cause']}`")
    meta.append("**处理级别：** L2（需 FAE 处理）")
    lines += ["　｜　".join(meta), ""]

    lines += ["##### 问题概述", output.get("symptom_summary", "—"), ""]
    lines += ["##### 疑似根因", output.get("suspected_root_cause", "—"), ""]
    indicators = output.get("key_abnormal_indicators") or []
    if indicators:
        lines += ["##### 关键异常指标", *[f"- {item}" for item in indicators], ""]

    rules = ticket.get("escalation_rules") or result.get("triggers") or []
    lines.append("##### 升级原因")
    lines += _rule_lines(rules) if rules else ["- 诊断根因本身属于需要 FAE 处理的类别。"]
    lines.append("")

    base = ticket.get("base_station")
    if base:
        codes = ", ".join(base.get("error_codes") or []) or "无"
        lines += ["##### 基站信息",
                  f"- 型号：{_fmt(base.get('model'))}　固件：{_fmt(base.get('fw'))}　"
                  f"状态：{'在线' if base.get('online') else '离线'}　故障码：{codes}", ""]

    devices = ticket.get("affected_devices") or []
    if devices:
        lines += ["##### 受影响设备",
                  "| 设备 | 型号 | 固件 | 信号 (RSSI) | 电量 | 状态 |",
                  "|---|---|---|---|---|---|"]
        for d in devices:
            lines.append(
                f"| {d.get('name') or d.get('id')} | {_fmt(d.get('model'))} | {_fmt(d.get('fw'))} | "
                f"{_fmt(d.get('rssi'), ' dBm')} | {_fmt(d.get('battery'), '%')} | "
                f"{DEVICE_STATUS.get(d.get('status'), _fmt(d.get('status')))} |")
        lines.append("")

    steps = ticket.get("steps_performed") or []
    lines.append("##### 一线已执行的排查")
    if steps:
        for i, step in enumerate(steps, 1):
            action, _, outcome = step.partition(" -> ")
            lines.append(f"{i}. {action}" + (f"  \n　→ 客户反馈：{outcome}" if outcome else ""))
    else:
        lines.append("- 未指导客户执行操作（证据已足以判断需要升级）。")
    return "\n".join(lines)


def _is_ticket(output):
    return bool(output.get("ticket") or output.get("symptom_summary"))


def _render_output(output, result=None):
    """Show the hand-off for frontline staff: steps, customer reply template, FAE ticket."""
    if output.get("repair_steps"):
        st.write("**一线操作步骤（供客服执行或指导客户）：**")
        for i, step in enumerate(output["repair_steps"], 1):
            st.write(f"{i}. {step}")
    if output.get("customer_reply"):
        st.write("**客户回复模板（客服可直接发送）：**")
        st.code(output["customer_reply"], language=None)
    if _is_ticket(output):
        ticket_md = _ticket_markdown(output, result)
        with st.container(border=True):
            st.markdown(ticket_md)
        st.download_button(
            "下载 FAE 工单（Markdown）",
            data=ticket_md,
            file_name=f"{(result or {}).get('case_id', 'case')}_FAE_ticket.md",
            mime="text/markdown",
            key=f"ticket_download_{(result or {}).get('system', '')}_{(result or {}).get('case_id', '')}",
        )


_INTERACTIVE_KEYS = ("interactive_diagnosis", "interactive_messages", "interactive_case_id", "interactive_error")
_ERRORS = (OpenAIError, RuntimeError, ValueError, OSError)


def _clear_interactive_state():
    for key in _INTERACTIVE_KEYS:
        st.session_state.pop(key, None)


_JUDGEMENT_LABELS = {True: "✅ 已解决", False: "❌ 未解决", None: "❔ 无法判断"}


def _judgement_message(judgement):
    label = _JUDGEMENT_LABELS[judgement.get("resolved")]
    reason = judgement.get("reason") or ""
    text = f"Agent 判断客户反馈：**{label}**" + (f"——{reason}" if reason else "")
    if judgement.get("resolved") is None:
        text += "（不计为修复失败，Agent 会继续确认）"
    return text


def _submit_reply(session, messages, answer):
    """Send the customer's reply (relayed by staff) and show the agent's next step."""
    from agent.interactive import SessionBusy

    if session.busy:
        st.info("上一条回复仍在处理中，请稍候，不要重复提交。")
        return
    was_action = session.pending["tool"] == "instruct_user"
    messages.append({"role": "user", "content": answer})
    with st.chat_message("user"):
        st.markdown(answer)
    try:
        with st.spinner("Agent 正在根据客户回复继续诊断，通常需要 5–20 秒…"):
            prompt = session.submit(answer)
    except SessionBusy:
        messages.pop()
        st.info("上一条回复仍在处理中，请稍候，不要重复提交。")
        return
    except _ERRORS as exc:
        if session.pending is not None:
            messages.pop()
            st.error(f"无法处理这条回复：{exc}")
            return
        st.session_state.interactive_error = f"处理回复时模型调用失败：{exc}"
        st.rerun()
    st.session_state.pop("interactive_error", None)
    if was_action and session.judgement:
        messages.append({"role": "assistant", "content": _judgement_message(session.judgement)})
    if prompt:
        messages.append({"role": "assistant", "content": prompt})
    st.rerun()


def _render_session_bar(session, case_id):
    """Status of the current ticket plus a confirmed 'abandon' action."""
    left, right = st.columns([4, 1], vertical_alignment="center")
    if session.result is not None:
        left.success(f"工单 {case_id} · 诊断已完成")
        return
    left.caption(f"工单 {case_id} · 进行中 · 第 {session.step} 步 / 最多 {session.max_steps} 步")
    with right.popover("放弃本次诊断", use_container_width=True):
        st.write("放弃后本次诊断进度不会保留，下次将从头开始处理该工单。")
        if st.button("确认放弃", type="primary", key=f"interactive_abandon_{case_id}"):
            session.abandon()
            _clear_interactive_state()
            st.rerun()


def _render_interactive(cases):
    st.subheader("一线客服工作台（Agent 副驾驶）")
    st.info(
        "你扮演一线客服，Agent 是你的副驾驶：它读取模拟支持台数据，建议你向客户确认的问题或指导客户执行的操作，"
        "你把客户的回答录入后它继续诊断，最后给出一线处理步骤、客户回复模板或 FAE 升级工单。"
        "Agent 不直接与客户对话；设备信息来自合成案例，当前没有连接真实设备。"
    )
    active = st.session_state.get("interactive_diagnosis")
    if active is not None:
        # lock the picker on the ticket being worked on
        st.session_state.interactive_case_picker = st.session_state.interactive_case_id
    case_id = st.selectbox(
        "选择要处理的客户案例", list(cases), key="interactive_case_picker",
        disabled=active is not None,
        help="处理中的工单完成或放弃后才能切换案例。" if active is not None else None,
    )
    case = cases[case_id]
    with st.expander("模拟客户可提供的信息（用于回答 Agent 的建议）"):
        st.write("请以该案例客户的口吻，根据以下已知信息回答 Agent 建议的问题；不需要猜测技术根因。")
        st.json(case.get("user_knowledge", {}))

    if active is None:
        if st.button("开始处理工单", type="primary"):
            from agent.interactive import InteractiveDiagnosis

            session = InteractiveDiagnosis(case)
            st.session_state.interactive_diagnosis = session
            st.session_state.interactive_case_id = case_id
            st.session_state.interactive_messages = [
                {"role": "user", "content": f"【客户投诉】{case['complaint']}"},
                {
                    "role": "assistant",
                    "content": (
                        "已恢复该工单上次未完成的诊断进度，可从下面的建议继续。"
                        if session.resumed else
                        "已为您调取客户投诉和模拟支持台数据。我会给出诊断建议，需要向客户确认的内容由您转达。"
                    ),
                },
            ]
            try:
                with st.spinner("Agent 正在读取支持台数据并分析，通常需要 5–20 秒…"):
                    prompt = session.start()
            except _ERRORS as exc:
                st.error(f"无法启动诊断：{exc}")
                _clear_interactive_state()
                return
            if prompt:
                st.session_state.interactive_messages.append(
                    {"role": "assistant", "content": prompt}
                )
            st.rerun()
        return

    session = active
    messages = st.session_state.interactive_messages
    _render_session_bar(session, case_id)
    if st.session_state.get("interactive_error"):
        st.error(st.session_state.interactive_error)
    if session.result is None and session.pending is None:
        st.warning("刚才没有完成下一步诊断。可重试模型请求，已提交的回复会保留。")
        if st.button("重试诊断", key=f"interactive_retry_{case_id}_{session.step}"):
            try:
                with st.spinner("Agent 正在重试分析…"):
                    prompt = session.resume()
            except _ERRORS as exc:
                st.session_state.interactive_error = f"重试诊断失败：{exc}"
                st.rerun()
            st.session_state.pop("interactive_error", None)
            if prompt:
                messages.append({"role": "assistant", "content": prompt})
            st.rerun()

    for message in messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if session.result is None and session.pending is not None:
        placeholder = ("录入客户操作后的反馈原话，例如：移近之后摄像头一整天都没掉线"
                       if session.pending["tool"] == "instruct_user" else "录入客户的回答")
        answer = st.chat_input(placeholder, key=f"interactive_reply_{case_id}")
        if answer and answer.strip():
            _submit_reply(session, messages, answer.strip())

    if session.result is not None:
        result = session.result
        expected_cause = case["gt_root_cause"]
        correct = result["pred_root_cause"] == expected_cause
        st.divider()
        st.subheader("诊断结果与处理建议")
        col1, col2 = st.columns(2)
        col1.metric(
            "诊断根因",
            result["pred_root_cause"],
            delta="与案例答案一致" if correct else "与案例答案不一致",
            delta_color="normal" if correct else "inverse",
        )
        col2.metric("处理分流（L1 一线闭环 / L2 升级 FAE）", result["pred_tier"])
        st.write(f"**诊断依据：** {result['rationale']}")
        if not _is_ticket(result["output"]):   # an FAE ticket already lists the rules
            _render_rules(result["triggers"])
        _render_output(result["output"], result)
        with st.expander("查看本次设备检查轨迹"):
            st.json(result["trace"])
        with st.expander("查看案例标准答案（诊断结束后显示）"):
            st.write(f"根因：{expected_cause} / {case['gt_tier']}")
            st.write(case.get("notes", ""))
        col1, col2 = st.columns(2)
        col1.download_button(
            "下载本次诊断记录",
            data=json.dumps(result, ensure_ascii=False, indent=2),
            file_name=f"{case_id}_interactive_diagnosis.json",
            mime="application/json",
            use_container_width=True,
        )
        if col2.button("处理下一个工单", type="primary", use_container_width=True,
                       key=f"interactive_next_{case_id}"):
            _clear_interactive_state()
            st.rerun()


def main():
    st.set_page_config(page_title="IoT Agent 可视化", page_icon="📡", layout="wide")
    st.title("📡 智能安防 IoT 一线客服副驾驶")
    st.caption("辅助一线客服完成拓扑感知诊断与 L1/L2 分流；浏览案例并查看评估结果。")

    try:
        cases = _load_cases()
        results = _load_results()
        taxonomy = yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
        st.error(f"读取项目数据失败：{exc}")
        st.stop()

    if not cases:
        st.error(f"案例目录中没有 JSON 文件：{CASES_DIR}")
        st.stop()

    view = st.sidebar.radio("页面", ["交互诊断", "案例总览", "案例浏览", "评估总览"])
    st.sidebar.caption(f"已加载 {len(cases)} 个案例 · {len(results)} 个评估系统")
    if view == "交互诊断":
        _render_interactive(cases)
    elif view == "案例总览":
        _render_case_overview(cases)
    elif view == "评估总览":
        _render_metrics(results)
    else:
        _render_case_browser(cases, results, taxonomy["root_causes"])


if __name__ == "__main__":
    main()
