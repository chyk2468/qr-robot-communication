"""
QR-Link: Visual Robot-to-Robot Optical Communication Protocol
Industrial Streamlit Dashboard
"""

import io
import json
import re
import time
from datetime import datetime, timezone
import numpy as np
from PIL import Image
import streamlit as st

# Import QR-Link Modular Packages
from encoder import (
    QRErrorCorrectionLevel,
    QREncoderConfig,
    generate_qr_image,
    generate_qr_bytes,
)
from decoder import (
    VisionDecoderEngine,
    VisionPreprocessingPipeline,
    decode_qr_image,
)
from protocol import (
    CommandType,
    PriorityLevel,
    Coordinates3D,
    NavigationParameters,
    DockParameters,
    ChargeParameters,
    ZoneAlertParameters,
    CustomParameters,
    RobotCommandMessage,
    ProtocolValidator,
    validate_protocol_message,
)
from security import (
    KeyPairHex,
    generate_ed25519_keypair,
    sign_canonical_payload,
    verify_payload_signature,
    AntiReplayGuard,
)
from robotics import (
    SimulatedRobotState,
    RoboticsControllerBridge,
)

# ---------------------------------------------------------
# Page Configuration & Global Styling
# ---------------------------------------------------------
st.set_page_config(
    page_title="QR-Link — Robot-to-Robot Optical Protocol",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Vanilla CSS
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    code, pre, .mono-text {
        font-family: 'JetBrains Mono', monospace !important;
    }

    .main-header {
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.1) 0%, rgba(139, 92, 246, 0.08) 50%, rgba(16, 185, 129, 0.05) 100%);
        border: 1px solid rgba(99, 102, 241, 0.25);
        border-radius: 16px;
        padding: 1.5rem 2rem;
        margin-bottom: 1.5rem;
    }

    .badge-primary {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        background: linear-gradient(135deg, #6366F1, #8B5CF6);
        color: white !important;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        padding: 0.3rem 0.75rem;
        border-radius: 9999px;
        margin-bottom: 0.5rem;
    }

    .chip {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        background: rgba(99, 102, 241, 0.08);
        border: 1px solid rgba(99, 102, 241, 0.2);
        color: #4F46E5;
        font-weight: 600;
        font-size: 0.825rem;
        padding: 0.25rem 0.65rem;
        border-radius: 8px;
    }

    .chip-success {
        background: rgba(16, 185, 129, 0.1);
        border: 1px solid rgba(16, 185, 129, 0.3);
        color: #059669;
    }

    .chip-danger {
        background: rgba(239, 68, 68, 0.1);
        border: 1px solid rgba(239, 68, 68, 0.3);
        color: #DC2626;
    }

    .chip-warning {
        background: rgba(245, 158, 11, 0.1);
        border: 1px solid rgba(245, 158, 11, 0.3);
        color: #D97706;
    }

    .glass-card {
        background: rgba(255, 255, 255, 0.7);
        border: 1px solid rgba(226, 232, 240, 0.9);
        border-radius: 12px;
        padding: 1.25rem;
        margin-bottom: 1rem;
        box-shadow: 0 4px 12px -2px rgba(0, 0, 0, 0.03);
    }

    @media (prefers-color-scheme: dark) {
        .glass-card {
            background: rgba(30, 41, 59, 0.6);
            border: 1px solid rgba(51, 65, 85, 0.8);
        }
        .chip {
            background: rgba(99, 102, 241, 0.2);
            color: #A5B4FC;
        }
        .chip-success {
            background: rgba(16, 185, 129, 0.2);
            color: #6EE7B7;
        }
        .chip-danger {
            background: rgba(239, 68, 68, 0.2);
            color: #FCA5A5;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------
if "keypair" not in st.session_state:
    st.session_state.keypair = generate_ed25519_keypair()

if "sequence_counter" not in st.session_state:
    st.session_state.sequence_counter = 101

if "anti_replay_guard" not in st.session_state:
    st.session_state.anti_replay_guard = AntiReplayGuard(max_skew_seconds=15.0)

if "robotics_bridge" not in st.session_state:
    st.session_state.robotics_bridge = RoboticsControllerBridge(
        SimulatedRobotState(robot_id="ROBOT_AMR_B", pos_x=0.0, pos_y=0.0, heading_deg=0.0)
    )

if "last_generated_qr_png" not in st.session_state:
    st.session_state.last_generated_qr_png = None

if "last_generated_payload_str" not in st.session_state:
    st.session_state.last_generated_payload_str = ""

if "security_audit_log" not in st.session_state:
    st.session_state.security_audit_log = []

# ---------------------------------------------------------
# Sidebar Controls & Agent Identity
# ---------------------------------------------------------
with st.sidebar:
    st.markdown("### 🤖 Agent Identities")
    st.info(f"**Transmitter:** `ROBOT_A_TX`\n\n**Receiver:** `ROBOT_B_RX`")
    
    st.divider()
    st.markdown("### 🔐 Cryptographic Keyring")
    st.markdown(f"**Ed25519 Public Key (TX):**")
    st.code(st.session_state.keypair.public_key_hex[:24] + "...", language="text")
    
    if st.button("🔄 Regenerate Asymmetric Keypair", use_container_width=True):
        st.session_state.keypair = generate_ed25519_keypair()
        st.success("New Ed25519 Keypair Generated!")
        st.rerun()

    st.divider()
    st.markdown("### 🛡️ Anti-Replay Guard Status")
    cached_nonces = len(st.session_state.anti_replay_guard.nonce_cache)
    st.markdown(f"- **Active TTL Nonces:** `{cached_nonces}`")
    st.markdown(f"- **Max Allowed Skew:** `±15.0s`")
    
    if st.button("🧹 Clear Nonce & Replay Cache", use_container_width=True):
        st.session_state.anti_replay_guard.reset_state()
        st.success("Replay cache cleared!")
        st.rerun()

    st.divider()
    st.markdown(
        """
        <div style="font-size: 0.8rem; color: #94A3B8;">
            <strong>QR-Link Protocol v1.0.0</strong><br>
            Zero-RF Optical Data Transport Layer
        </div>
        """,
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------
# Header Banner
# ---------------------------------------------------------
st.markdown(
    """
    <div class="main-header">
        <div class="badge-primary">◈ QR-Link Optical Protocol</div>
        <h1 style="margin:0; font-size:2.2rem; font-weight:800; letter-spacing:-0.03em;">
            Visual Robot-to-Robot Communication System
        </h1>
        <p style="margin:0.4rem 0 0 0; color:#64748B; font-size:1rem;">
            Air-gapped, zero-RF optical data transport layer for autonomous robotics coordination, line-of-sight command validation, and anti-replay telemetry dispatch.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# Main Tabs
# ---------------------------------------------------------
tab_tx, tab_rx, tab_sec, tab_specs = st.tabs([
    "📡 1. TRANSMITTER (Robot A / Operator)",
    "📷 2. RECEIVER & ACTUATION (Robot B)",
    "🛡️ 3. SECURITY & REPLAY ATTACK LAB",
    "📘 4. PROTOCOL & SYSTEM SPECS",
])

# =========================================================
# TAB 1: TRANSMITTER (ROBOT A / OPERATOR)
# =========================================================
with tab_tx:
    col_form, col_qr = st.columns([1.1, 0.9], gap="large")

    with col_form:
        st.subheader("1. Command Payload Formatter")
        
        mode = st.radio(
            "Payload Format Mode:",
            options=["Structured Robotic Protocol (Standard)", "Unstructured / Raw Text (Legacy)"],
            horizontal=True,
        )

        final_payload_str = ""

        if mode == "Structured Robotic Protocol (Standard)":
            c_type = st.selectbox(
                "Command Type:",
                options=[
                    "NAVIGATE_TO (Waypoint / Bay Navigation)",
                    "DOCK (Precision Docking Bay)",
                    "CHARGE (Automated Charging Station)",
                    "ZONE_ALERT (Hazard / Obstruction Broadcast)",
                    "EMERGENCY_STOP (Instant Optical Halt)",
                    "CUSTOM (User Parameterized)",
                ],
            )

            col_id1, col_id2 = st.columns(2)
            with col_id1:
                sender_id = st.text_input("Sender ID:", value="ROBOT_AMR_01")
            with col_id2:
                receiver_id = st.text_input("Receiver ID:", value="ROBOT_AMR_02")

            priority_map = {"NORMAL": PriorityLevel.NORMAL, "HIGH": PriorityLevel.HIGH, "CRITICAL": PriorityLevel.CRITICAL, "LOW": PriorityLevel.LOW}
            
            # Form fields per command type
            if "NAVIGATE_TO" in c_type:
                c1, c2 = st.columns(2)
                with c1:
                    target_zone = st.text_input("Target Zone:", value="WAREHOUSE_BAY_03")
                    v_max = st.slider("Max Linear Speed (m/s):", 0.1, 3.0, 0.75, 0.05)
                with c2:
                    p_sel = st.selectbox("Priority:", options=["NORMAL", "HIGH", "CRITICAL", "LOW"], index=0)
                    w_max = st.slider("Max Angular Speed (rad/s):", 0.1, 3.14, 1.0, 0.05)

                st.markdown("##### 📍 Target 3D Coordinates")
                co1, co2, co3, co4 = st.columns(4)
                with co1:
                    coord_x = st.number_input("X (m):", value=14.5, step=0.5)
                with co2:
                    coord_y = st.number_input("Y (m):", value=22.0, step=0.5)
                with co3:
                    coord_z = st.number_input("Z (m):", value=0.0, step=0.1)
                with co4:
                    yaw = st.number_input("Yaw (°):", value=90.0, step=15.0)

                params_obj = NavigationParameters(
                    target_zone=target_zone,
                    coordinates=Coordinates3D(x=coord_x, y=coord_y, z=coord_z, yaw_deg=yaw),
                    linear_velocity_max=v_max,
                    angular_velocity_max=w_max,
                    priority=priority_map[p_sel],
                    timeout_sec=60,
                )
                cmd_enum = CommandType.NAVIGATE_TO

            elif "DOCK" in c_type:
                c1, c2 = st.columns(2)
                with c1:
                    bay_id = st.text_input("Docking Bay ID:", value="DOCK_BAY_NORTH_02")
                with c2:
                    approach_spd = st.slider("Approach Speed (m/s):", 0.05, 0.5, 0.2, 0.05)
                latch = st.checkbox("Mechanical Latch Engagement Required", value=True)
                params_obj = DockParameters(bay_id=bay_id, approach_speed=approach_spd, latch_required=latch)
                cmd_enum = CommandType.DOCK

            elif "CHARGE" in c_type:
                c1, c2 = st.columns(2)
                with c1:
                    station_id = st.text_input("Charging Station ID:", value="CHARGE_STATION_ALPHA")
                    bay_idx = st.number_input("Bay Index / Slot:", min_value=1, max_value=16, value=2)
                with c2:
                    soc_target = st.slider("Target State of Charge (%):", 20.0, 100.0, 90.0, 5.0)
                params_obj = ChargeParameters(station_id=station_id, bay_index=bay_idx, target_soc_pct=soc_target)
                cmd_enum = CommandType.CHARGE

            elif "ZONE_ALERT" in c_type:
                c1, c2 = st.columns(2)
                with c1:
                    zone_id = st.text_input("Hazard Zone ID:", value="ZONE_AISLE_07")
                    alert_type = st.selectbox("Hazard Classification:", options=["OBSTRUCTION", "LIQUID_SPILL", "FIRE_ALARM", "EQUIPMENT_FAULT"])
                with c2:
                    sev = st.selectbox("Severity:", options=["HIGH", "CRITICAL", "NORMAL"], index=0)
                params_obj = ZoneAlertParameters(zone_id=zone_id, alert_type=alert_type, severity=priority_map[sev])
                cmd_enum = CommandType.ZONE_ALERT

            elif "EMERGENCY_STOP" in c_type:
                st.error("🚨 EMERGENCY OPTICAL STOP: Instructs all line-of-sight robots to immediately halt motors.")
                params_obj = CustomParameters(action="EMERGENCY_STOP", arguments={"reason": "Manual operator visual E-STOP"})
                cmd_enum = CommandType.EMERGENCY_STOP

            else:
                action_name = st.text_input("Custom Action Name:", value="INVENTORY_SCAN")
                arg_json = st.text_area("Arguments (JSON dict):", value='{"shelf_id": "S-401", "scan_depth": 2}', height=80)
                try:
                    parsed_args = json.loads(arg_json)
                except Exception:
                    parsed_args = {"raw": arg_json}
                params_obj = CustomParameters(action=action_name, arguments=parsed_args)
                cmd_enum = CommandType.CUSTOM

            # Security Signing Controls
            st.markdown("---")
            st.markdown("##### 🔐 Cryptographic Authentication")
            enable_sign = st.checkbox("Sign Payload with Ed25519 Asymmetric Key", value=True)
            
            st.session_state.sequence_counter += 1
            current_seq = st.session_state.sequence_counter
            current_time_iso = datetime.now(timezone.utc).isoformat()

            # Construct RobotCommandMessage
            robot_msg = RobotCommandMessage(
                sender_id=sender_id,
                receiver_id=receiver_id,
                sequence_num=current_seq,
                timestamp_utc=current_time_iso,
                command=cmd_enum,
                parameters=params_obj,
            )

            # Produce canonical payload and sign
            payload_dict = robot_msg.model_dump()
            if enable_sign:
                signature_hex = sign_canonical_payload(payload_dict, st.session_state.keypair.private_key_hex)
                payload_dict["security"]["auth_type"] = "ED25519"
                payload_dict["security"]["public_key"] = st.session_state.keypair.public_key_hex
                payload_dict["security"]["signature"] = signature_hex
            else:
                payload_dict["security"]["auth_type"] = "NONE"
                payload_dict["security"]["public_key"] = None
                payload_dict["security"]["signature"] = None

            final_payload_str = json.dumps(payload_dict, separators=(",", ":"))

        else:
            # Unstructured Text Mode
            raw_input = st.text_area(
                "Enter raw command or text string:",
                value="MOVE_FORWARD;SPEED=0.5;DIST=2.0",
                height=140,
            )
            final_payload_str = raw_input.strip()

        st.session_state.last_generated_payload_str = final_payload_str

    with col_qr:
        st.subheader("2. Dynamic QR Optical Generator")

        with st.expander("⚙️ Optical Modulation & Styling", expanded=False):
            err_corr_label = st.selectbox(
                "Error Correction Level (Reed-Solomon):",
                options=[
                    QRErrorCorrectionLevel.HIGH.value,
                    QRErrorCorrectionLevel.QUARTILE.value,
                    QRErrorCorrectionLevel.MEDIUM.value,
                    QRErrorCorrectionLevel.LOW.value,
                ],
                index=0,
                help="High (30%) is recommended for harsh robotics environments with dust, glare, or motion blur.",
            )
            err_map = {
                QRErrorCorrectionLevel.HIGH.value: QRErrorCorrectionLevel.HIGH,
                QRErrorCorrectionLevel.QUARTILE.value: QRErrorCorrectionLevel.QUARTILE,
                QRErrorCorrectionLevel.MEDIUM.value: QRErrorCorrectionLevel.MEDIUM,
                QRErrorCorrectionLevel.LOW.value: QRErrorCorrectionLevel.LOW,
            }
            
            c_box, c_border = st.columns(2)
            with c_box:
                box_sz = st.slider("Box Resolution (px/module):", 4, 16, 8)
            with c_border:
                border_sz = st.slider("Quiet Zone Margin:", 1, 8, 4)

            c_fg, c_bg = st.columns(2)
            with c_fg:
                fg_col = st.color_picker("Foreground Color:", value="#0F172A")
            with c_bg:
                bg_col = st.color_picker("Background Color:", value="#FFFFFF")

        if final_payload_str:
            enc_config = QREncoderConfig(
                error_correction=err_map[err_corr_label],
                box_size=box_sz,
                border=border_sz,
                fill_color=fg_col,
                back_color=bg_col,
            )

            qr_img, telemetry = generate_qr_image(final_payload_str, enc_config)
            png_bytes, _ = generate_qr_bytes(final_payload_str, enc_config)
            st.session_state.last_generated_qr_png = png_bytes

            st.image(qr_img, caption=f"QR-Link Optical Symbol ({qr_img.width}x{qr_img.height} px)", width=320)

            # Telemetry metrics
            m1, m2, m3 = st.columns(3)
            with m1:
                st.markdown(f'<div class="chip chip-success">📦 <strong>{telemetry.byte_length}</strong> Bytes</div>', unsafe_allow_html=True)
            with m2:
                st.markdown(f'<div class="chip">🛡️ Rec: <strong>{telemetry.error_recovery_pct}</strong></div>', unsafe_allow_html=True)
            with m3:
                st.markdown(f'<div class="chip">📐 Ver: <strong>{telemetry.matrix_version or "Auto"}</strong></div>', unsafe_allow_html=True)

            st.write("")
            st.download_button(
                label="📥 Download Optical Symbol (PNG)",
                data=png_bytes,
                file_name="qr_link_symbol.png",
                mime="image/png",
                type="primary",
                use_container_width=True,
            )

            with st.expander("👁️ Inspect Raw Serialized JSON Payload", expanded=False):
                st.code(final_payload_str, language="json")


# =========================================================
# TAB 2: RECEIVER (ROBOT B VISION & ACTUATION)
# =========================================================
with tab_rx:
    col_input, col_diag = st.columns([1, 1], gap="large")

    with col_input:
        st.subheader("1. Optical Ingestion (Robot B Camera)")

        input_src = st.radio(
            "Frame Capture Method:",
            options=["Upload Image / Camera Snapshot", "Live Webcam Capture", "Direct Optical Loopback (Transmitter Cache)"],
            horizontal=True,
        )

        image_to_decode = None

        if input_src == "Upload Image / Camera Snapshot":
            uploaded = st.file_uploader("Upload Frame (`.png`, `.jpg`, `.jpeg`, `.bmp`):", type=["png", "jpg", "jpeg", "bmp", "webp"])
            if uploaded:
                image_to_decode = Image.open(uploaded).convert("RGB")

        elif input_src == "Live Webcam Capture":
            cam_photo = st.camera_input("Point Robot B Camera at Robot A Display:")
            if cam_photo:
                image_to_decode = Image.open(cam_photo).convert("RGB")

        else:
            if st.session_state.last_generated_qr_png is not None:
                st.success("✅ Feeding currently synthesized QR matrix from Transmitter into Robot B optical pipeline.")
                image_to_decode = Image.open(io.BytesIO(st.session_state.last_generated_qr_png)).convert("RGB")
            else:
                st.info("No QR code synthesized yet in Transmitter. Generate one first or upload an image.")

        if image_to_decode is not None:
            st.image(image_to_decode, caption="Ingested Raw Optical Frame", width=300)

    with col_diag:
        st.subheader("2. Computer Vision Decoding & Validation")

        if image_to_decode is not None:
            # 1. Run Decoder Engine
            decode_res = decode_qr_image(image_to_decode)

            if decode_res.success and decode_res.payload:
                st.markdown(f'<div class="chip chip-success">⚡ Decoded via <strong>{decode_res.stage_used}</strong> ({decode_res.latency_ms} ms)</div>', unsafe_allow_html=True)
                
                if decode_res.annotated_image:
                    st.image(decode_res.annotated_image, caption="Computer Vision Detection & Quadrilateral Bounding Box", width=280)

                raw_text = decode_res.payload

                # 2. Protocol Validation
                val_res = validate_protocol_message(raw_text)

                st.markdown("#### 🔍 Security & Schema Verification")

                if val_res.is_valid and val_res.message:
                    msg: RobotCommandMessage = val_res.message

                    # Perform Cryptographic Verification
                    sig_hex = msg.security.signature
                    pub_hex = msg.security.public_key
                    auth_type = msg.security.auth_type

                    if auth_type == "ED25519" and sig_hex and pub_hex:
                        sig_valid = verify_payload_signature(msg.model_dump(), sig_hex, pub_hex)
                    else:
                        sig_valid = False

                    # Anti-Replay and Temporal Check
                    sec_check = st.session_state.anti_replay_guard.verify_message_integrity(
                        sender_id=msg.sender_id,
                        sequence_num=msg.sequence_num,
                        timestamp_iso=msg.timestamp_utc,
                        nonce=msg.nonce,
                        signature_valid=sig_valid if auth_type == "ED25519" else True,
                    )

                    # Display Status Badges
                    b1, b2 = st.columns(2)
                    with b1:
                        if auth_type == "ED25519":
                            if sig_valid:
                                st.markdown('<div class="chip chip-success">🔒 Ed25519 Signature: <strong>VALID</strong></div>', unsafe_allow_html=True)
                            else:
                                st.markdown('<div class="chip chip-danger">❌ Ed25519 Signature: <strong>FORGED/CORRUPT</strong></div>', unsafe_allow_html=True)
                        else:
                            st.markdown('<div class="chip chip-warning">⚠️ Payload is <strong>UNSIGNED</strong></div>', unsafe_allow_html=True)

                    with b2:
                        if sec_check.timestamp_fresh:
                            st.markdown(f'<div class="chip chip-success">⏱️ Freshness: <strong>{sec_check.time_delta_seconds}s</strong></div>', unsafe_allow_html=True)
                        else:
                            st.markdown(f'<div class="chip chip-danger">⏱️ Time Drift: <strong>{sec_check.time_delta_seconds}s (EXPIRED)</strong></div>', unsafe_allow_html=True)

                    b3, b4 = st.columns(2)
                    with b3:
                        if sec_check.nonce_unique:
                            st.markdown('<div class="chip chip-success">🔑 Nonce: <strong>UNIQUE</strong></div>', unsafe_allow_html=True)
                        else:
                            st.markdown('<div class="chip chip-danger">🚨 Replay: <strong>DUPLICATE NONCE</strong></div>', unsafe_allow_html=True)

                    with b4:
                        if sec_check.sequence_valid:
                            st.markdown(f'<div class="chip chip-success">🔢 Seq: <strong>#{msg.sequence_num} OK</strong></div>', unsafe_allow_html=True)
                        else:
                            st.markdown(f'<div class="chip chip-danger">🔢 Seq: <strong>#{msg.sequence_num} OUT OF ORDER</strong></div>', unsafe_allow_html=True)

                    # 3. Kinematic Actuation & ROS 2 Bridge Dispatch
                    st.divider()
                    st.markdown("#### ⚙️ Robot Actuation & ROS 2 Kinematics")

                    if sec_check.passed or (auth_type == "NONE" and sec_check.timestamp_fresh):
                        exec_result = st.session_state.robotics_bridge.process_command(msg)
                        st.success(f"🚀 **Action Dispatched:** {exec_result.status_summary}")

                        # Telemetry Cards
                        st.markdown("##### 📊 Live Robot B State Telemetry")
                        tel_c1, tel_c2, tel_c3 = st.columns(3)
                        r_state = exec_result.updated_state
                        with tel_c1:
                            st.metric("Position (X, Y)", f"{r_state.pos_x:.1f} m, {r_state.pos_y:.1f} m")
                        with tel_c2:
                            st.metric("Linear Velocity", f"{r_state.linear_velocity:.2f} m/s")
                        with tel_c3:
                            st.metric("Battery State", f"{r_state.battery_soc_pct:.0f} %")

                        with st.expander("📡 Inspect ROS 2 Topic Dispatches", expanded=False):
                            for d in exec_result.ros2_dispatches:
                                st.markdown(f"**Topic:** `{d.topic_name}` (`{d.message_type}`)")
                                st.json(d.payload_dict)

                    else:
                        st.error("⛔ **ACTUATION BLOCKED BY SECURITY GUARD**")
                        for err in sec_check.error_reasons:
                            st.markdown(f"- 🛑 {err}")

                else:
                    st.warning("⚠️ Received Unstructured / Legacy Payload (Non-JSON)")
                    st.markdown(f"**Decoded Content:**")
                    st.code(raw_text)

            else:
                st.error("❌ Optical Detection Failed: No valid QR finder patterns located in image.")
                st.info("Tip: Ensure high contrast, sufficient lighting, and unblurred finder corners.")
        else:
            st.info("Select or upload an optical frame on the left to begin decoding.")


# =========================================================
# TAB 3: SECURITY & REPLAY ATTACK LAB
# =========================================================
with tab_sec:
    st.subheader("🛡️ Optical Security & Threat Simulation Sandbox")
    st.markdown(
        """
        Test the mathematical resilience of the QR-Link protocol against real-world adversarial attacks:
        **Payload Tampering**, **Replay Attacks**, and **Timestamp Drift**.
        """
    )

    attack_type = st.selectbox(
        "Select Attack Scenario to Simulate:",
        options=[
            "1. In-Flight Payload Tampering (MITM Modification of Speed/Target)",
            "2. Visual Recording Replay Attack (Re-transmitting Stale Captured QR)",
            "3. Expired Timestamp Drift (Attacking Stale Cached Instructions)",
            "4. Signature Forgery (Using Unauthorized Rogue Private Key)",
        ],
    )

    col_sim_in, col_sim_out = st.columns([1, 1], gap="large")

    with col_sim_in:
        st.markdown("##### 🎯 Attack Injection Controls")

        # Generate a standard baseline payload
        baseline_keypair = generate_ed25519_keypair()
        baseline_msg = RobotCommandMessage(
            sender_id="ROBOT_AMR_01",
            receiver_id="ROBOT_AMR_02",
            sequence_num=501,
            command=CommandType.NAVIGATE_TO,
            parameters=NavigationParameters(target_zone="SAFE_BAY_A", linear_velocity_max=0.5),
        )
        base_dict = baseline_msg.model_dump()
        base_sig = sign_canonical_payload(base_dict, baseline_keypair.private_key_hex)
        base_dict["security"] = {
            "auth_type": "ED25519",
            "public_key": baseline_keypair.public_key_hex,
            "signature": base_sig,
        }

        if "1. In-Flight Payload Tampering" in attack_type:
            st.markdown("An attacker intercepts the visual display and modifies `linear_velocity_max` from `0.5` to `9.99` m/s.")
            tampered_dict = json.loads(json.dumps(base_dict))
            tampered_dict["parameters"]["linear_velocity_max"] = 9.99
            test_payload = json.dumps(tampered_dict)
            st.code(test_payload, language="json")

        elif "2. Visual Recording Replay Attack" in attack_type:
            st.markdown("An attacker records a legitimate QR code from yesterday and replays it to trigger an unwanted movement.")
            test_payload = json.dumps(base_dict)
            st.code(test_payload, language="json")
            # Pre-register nonce to simulate replay
            st.session_state.anti_replay_guard.nonce_cache[base_dict["nonce"]] = time.time() + 300.0

        elif "3. Expired Timestamp Drift" in attack_type:
            st.markdown("Simulating a delayed optical packet that took 120 seconds to reach the receiver.")
            drifted_dict = json.loads(json.dumps(base_dict))
            drifted_dict["timestamp_utc"] = "2020-01-01T00:00:00Z"
            # Recompute signature for expired time
            drifted_sig = sign_canonical_payload(drifted_dict, baseline_keypair.private_key_hex)
            drifted_dict["security"]["signature"] = drifted_sig
            test_payload = json.dumps(drifted_dict)
            st.code(test_payload, language="json")

        else:
            st.markdown("An attacker creates a malicious command signed with a rogue key.")
            rogue_keypair = generate_ed25519_keypair()
            rogue_dict = json.loads(json.dumps(base_dict))
            rogue_sig = sign_canonical_payload(rogue_dict, rogue_keypair.private_key_hex)
            # Attacker presents legitimate public key but signs with rogue private key
            rogue_dict["security"]["signature"] = rogue_sig
            test_payload = json.dumps(rogue_dict)
            st.code(test_payload, language="json")

        run_attack_btn = st.button("🚀 Ingest Attack Payload into Robot B Security Guard", type="primary", use_container_width=True)

    with col_sim_out:
        st.markdown("##### 🛡️ Robot B Defense Verification Verdict")

        if run_attack_btn:
            val = validate_protocol_message(test_payload)
            if val.is_valid and val.message:
                m = val.message
                is_sig_ok = verify_payload_signature(m.model_dump(), m.security.signature or "", m.security.public_key or "")
                sec = st.session_state.anti_replay_guard.verify_message_integrity(
                    sender_id=m.sender_id,
                    sequence_num=m.sequence_num,
                    timestamp_iso=m.timestamp_utc,
                    nonce=m.nonce,
                    signature_valid=is_sig_ok,
                )

                if sec.passed:
                    st.error("❌ CRITICAL: Attack bypassed defenses! (Unexpected)")
                else:
                    st.success("✅ **DEFENSE SUCCESS: Malicious optical payload successfully neutralized.**")
                    for reason in sec.error_reasons:
                        st.markdown(f"- 🛑 **Security Failure:** `{reason}`")
                    st.info("Robot B safety controller refused to dispatch kinematic motor instructions.")
            else:
                st.success("✅ **DEFENSE SUCCESS:** Schema validation rejected malformed syntax.")


# =========================================================
# TAB 4: PROTOCOL & SYSTEM SPECS
# =========================================================
with tab_specs:
    st.subheader("📘 QR-Link Protocol & Architecture Specifications")

    col_s1, col_s2 = st.columns(2, gap="large")

    with col_s1:
        st.markdown("#### 📑 Standard JSON Message Contract")
        sample_contract = {
            "schema_version": "1.0.0",
            "sender_id": "ROBOT_A",
            "receiver_id": "ROBOT_B",
            "message_id": "MSG-98421b0e",
            "sequence_num": 10482,
            "timestamp_utc": "2026-08-17T09:30:00.125Z",
            "nonce": "a7f89bc102e3",
            "command": "NAVIGATE_TO",
            "parameters": {
                "target_zone": "BAY_03",
                "coordinates": {"x": 12.45, "y": 88.10, "z": 0.0, "yaw_deg": 90.0},
                "linear_velocity_max": 0.75,
                "angular_velocity_max": 1.0,
                "priority": "HIGH",
                "timeout_sec": 60,
            },
            "security": {
                "auth_type": "ED25519",
                "public_key": "4a7b...89c1",
                "signature": "3b6a...f89c",
            },
        }
        st.json(sample_contract)

    with col_s2:
        st.markdown("#### 📊 Communication Channel Performance Matrix")
        st.markdown(
            """
            | Parameter | Optical QR-Link | Industrial Wi-Fi (802.11ax) | BLE 5.0 |
            | :--- | :---: | :---: | :---: |
            | **Physical Spectrum** | **Visible Light (Zero RF)** | 2.4 / 5.0 GHz | 2.4 GHz |
            | **Line-of-Sight** | **Mandatory** | Not Required | Partial |
            | **EMI Susceptibility** | **0% (Immune)** | High | High |
            | **Throughput** | Sub-kilobyte / packet | $>100$ Mbps | $\approx 1$ Mbps |
            | **Infrastructure Cost** | **Zero (Camera Reuse)** | High (Access Points) | Low |
            | **Eavesdrop Boundary** | Physical Line-of-Sight | Penetrates Walls | Penetrates Walls |
            """
        )

# ---------------------------------------------------------
# Footer
# ---------------------------------------------------------
st.divider()
st.markdown(
    """
    <div style="text-align: center; color: #94A3B8; font-size: 0.85rem; padding-bottom: 1rem;">
        🤖 <strong>QR-Link:</strong> Visual Robot-to-Robot Optical Communication Protocol | Python • Streamlit • OpenCV • Ed25519 • Pydantic v2
    </div>
    """,
    unsafe_allow_html=True,
)
