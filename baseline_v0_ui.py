"""Giao diện Streamlit cho Visual QC Agent MVP."""

from __future__ import annotations

import requests
import streamlit as st

API_BASE_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="Visual QC Agent MVP", page_icon="🚗", layout="wide")

st.title("🚗 Visual QC Agent - Baseline MVP")
st.caption("Hệ thống tự động kiểm tra PASS/FAIL - QC chỉ can thiệp vào ca REVIEW")


def call_inspect_api() -> dict:
    response = requests.post(f"{API_BASE_URL}/api/inspect", json={"use_random": True}, timeout=10)
    response.raise_for_status()
    return response.json()


def call_override_api(surface: str, status: str, reason: str) -> None:
    payload = {"surface": surface, "status": status, "reason": reason}
    response = requests.post(f"{API_BASE_URL}/api/override", json=payload, timeout=10)
    response.raise_for_status()


if "inspection_result" not in st.session_state:
    st.session_state.inspection_result = None

col1, col2 = st.columns([2, 1])
with col1:
    if st.button("🚀 Bắt đầu Scan xe mới (Trigger Camera)", use_container_width=True):
        try:
            with st.spinner("Đang phân tích 5 mặt xe..."):
                result = call_inspect_api()
                st.session_state.inspection_result = result
                st.toast("Scan hoàn tất!", icon="✅")
        except Exception as exc:
            st.error(f"Không thể kết nối API: {exc}")

with col2:
    st.markdown("**Quy trình QC:**")
    st.write("🟢 **PASS / 🔴 FAIL:** Tự động chốt kết quả.")
    st.write("🟡 **REVIEW:** Cần QC bấm xác nhận bên dưới.")

result = st.session_state.inspection_result
if result is not None:
    st.markdown("---")
    st.subheader(f"Mã lượt kiểm định: {result.get('inspection_id')}")

    surfaces = result.get("surfaces", [])
    for surface in surfaces:
        surface_name = surface.get("surface", "unknown")
        status = surface.get("status", "REVIEW")
        reason = surface.get("reason", "")
        quality = surface.get("image_quality", 0)
        detections = surface.get("detections", [])

        color_map = {"PASS": "#16a34a", "FAIL": "#dc2626", "REVIEW": "#ca8a04"}
        border_color = color_map.get(status, "#6b7280")

        st.markdown(
            f"<div style='border:2px solid {border_color}; border-radius:10px; padding:12px; margin-bottom:10px;'>",
            unsafe_allow_html=True,
        )
        
        # Header mỗi mặt xe
        st.markdown(
            f"#### {surface_name.upper()} — <span style='color:{border_color};'>{status}</span>",
            unsafe_allow_html=True,
        )

        col_a, col_b, col_c = st.columns([1.5, 1.5, 2])
        with col_a:
            st.write(f"• **Chất lượng ảnh:** {quality}%")
            if detections:
                st.write("• **Lỗi phát hiện:**")
                for det in detections:
                    st.write(f"  - {det['type']} | Độ tin cậy: {det['confidence']*100:.0f}% | Kích thước: {det['size_mm']}mm")
            else:
                st.write("• **Lỗi phát hiện:** Không có")

        with col_b:
            st.write("• **Bounding Box:**")
            if detections:
                for det in detections:
                    st.write(f"  - {det['bounding_box']}")
            else:
                st.write("  - N/A")

        with col_c:
            st.write("• **Lý giải từ Agent:**")
            st.info(reason)

        # 🎯 CHỈ HIỂN THỊ NÚT BẤM KHI TRẠNG THÁI LÀ REVIEW HOẶC CẦN QC XÁC NHẬN
        if status == "REVIEW" or "[QC OVERRIDE]" in reason:
            st.caption("👉 **QC Cần can thiệp quyết định cho mặt này:**")
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if st.button(f"Confirm PASS · {surface_name.upper()}", key=f"pass_{surface_name}"):
                    try:
                        call_override_api(surface_name, "PASS", "QC xác nhận đạt chuẩn")
                        st.toast(f"✅ Đã chốt PASS cho {surface_name.upper()}!", icon="🎉")
                        # Cập nhật lại UI dựa trên dữ liệu mới mà không bị xóa màn hình
                        for s in st.session_state.inspection_result["surfaces"]:
                            if s["surface"] == surface_name:
                                s["status"] = "PASS"
                                s["reason"] = "[QC OVERRIDE]: QC xác nhận đạt chuẩn"
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Thất bại: {exc}")

            with btn_col2:
                if st.button(f"Confirm FAIL · {surface_name.upper()}", key=f"fail_{surface_name}"):
                    try:
                        call_override_api(surface_name, "FAIL", "QC xác nhận lỗi không đạt")
                        st.toast(f"❌ Đã chốt FAIL cho {surface_name.upper()}!", icon="🚨")
                        for s in st.session_state.inspection_result["surfaces"]:
                            if s["surface"] == surface_name:
                                s["status"] = "FAIL"
                                s["reason"] = "[QC OVERRIDE]: QC xác nhận lỗi không đạt"
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Thất bại: {exc}")
        else:
            st.caption("⚡ *Hệ thống tự động xử lý (Không cần thao tác manual).*")

        st.markdown("</div>", unsafe_allow_html=True)

else:
    st.info("Nhấn 'Bắt đầu Scan xe mới' để chạy lượt kiểm thử tiếp theo.")