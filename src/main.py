# main.py
from flask import Flask, render_template, request, send_file, jsonify, after_this_request, send_from_directory
import os
import tempfile
import zipfile
import json
import shutil
import logging
import traceback
import re
import uuid
from collections import defaultdict
from werkzeug.utils import secure_filename

# pyedb
from pyedb import Edb

# -------------------- App & Config --------------------
app = Flask(__name__, template_folder='templates')
# Use absolute path for UPLOAD_FOLDER to avoid ambiguity between CWD and app root
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
app.config['UPLOAD_FOLDER'] = os.path.join(project_root, 'output')
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 1GB
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

logging.basicConfig(level=logging.DEBUG)
app.logger.setLevel(logging.DEBUG)

EDB_VERSION = "2024.1"  # 依環境調整，或設為 None 讓 pyedb 自動偵測

# -------------------- Utils --------------------
def safe_extract(zip_path: str, dest_dir: str) -> None:
    """避免 zip slip 的安全解壓。"""
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for member in zf.infolist():
            member_path = os.path.join(dest_dir, member.filename)
            abs_dest = os.path.abspath(dest_dir)
            abs_target = os.path.abspath(member_path)
            if not abs_target.startswith(abs_dest + os.sep) and abs_target != abs_dest:
                raise ValueError("Illegal file path in zip (zip slip attempt)")
        zf.extractall(dest_dir)

def find_aedb_folder(root_dir: str) -> str:
    """遞迴尋找 .aedb 目錄。"""
    for cur, dirs, _ in os.walk(root_dir):
        for d in dirs:
            if d.lower().endswith(".aedb"):
                return os.path.join(cur, d)
    return ""

_pin_tup_re = re.compile(r"\(\s*([^,\s)]+)\s*,\s*([^)]+?)\s*\)$")

def parse_tuple(s: str):
    """
    將字串形式的 (comp, net) 還原成 tuple
    例如 "(J2L1, GPIO_SUS3_PCIE_RESET_N)" -> ("J2L1", "GPIO_SUS3_PCIE_RESET_N")
    """
    if not isinstance(s, str):
        raise ValueError(f"pin must be string, got {type(s)}")
    m = _pin_tup_re.match(s.strip())
    if not m:
        raise ValueError(f"Invalid pin tuple format: {s}")
    return m.group(1).strip(), m.group(2).strip()

def get_pin_net_name(pin) -> str:
    """同時相容 pin.net_name 和 pin.net.name。"""
    n = getattr(pin, "net_name", None)
    if n:
        return n
    net = getattr(pin, "net", None)
    return getattr(net, "name", None)

def zip_aedb_folder(src_aedb_folder: str, out_zip_path: str):
    """
    將 src_aedb_folder 的內容壓成 out_zip_path，且 zip 內不含根目錄。
    """
    if os.path.exists(out_zip_path):
        os.remove(out_zip_path)
    with zipfile.ZipFile(out_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        base = os.path.abspath(src_aedb_folder)
        for root, _, files in os.walk(base):
            for f in files:
                abs_path = os.path.join(root, f)
                arcname = os.path.relpath(abs_path, base)
                zf.write(abs_path, arcname)

# -------------------- Routes --------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_aedb():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if not file.filename.lower().endswith('.zip'):
        return jsonify({'error': 'Invalid file type. Please upload a .zip file containing an .aedb folder'}), 400

    temp_dir = tempfile.mkdtemp(dir=app.config['UPLOAD_FOLDER'])
    app.logger.debug("UPLOAD temp_dir=%s", temp_dir)

    try:
        zip_name = secure_filename(file.filename)
        zip_path = os.path.join(temp_dir, zip_name)
        file.save(zip_path)

        safe_extract(zip_path, temp_dir)

        aedb_folder_path = find_aedb_folder(temp_dir)
        if not aedb_folder_path:
            raise FileNotFoundError('No .aedb folder found in the zip file')

        # 讀取 EDB 結構（唯讀開啟）
        type_comp = defaultdict(list)
        comp_pins = {}
        pin_net = {}
        net_pins = defaultdict(list)
        type_net = defaultdict(list)

        with Edb(aedb_folder_path, edbversion=EDB_VERSION, isreadonly=True) as edb:
            for comp_name, comp in edb.components.components.items():
                type_comp[comp.type].append(comp_name)
                comp_pins[comp_name] = list(comp.pins.keys())
                for pin_name, pin in comp.pins.items():
                    nname = get_pin_net_name(pin)
                    pin_net[f"{comp_name}:{pin_name}"] = nname
                    net_pins[nname].append((comp_name, pin_name))

            for net_name, net in edb.nets.nets.items():
                if net.is_power_ground:
                    type_net['power'].append(net_name)
                else:
                    type_net['signal'].append(net_name)

        info = {
            'type_comp': dict(type_comp),
            'comp_pins': comp_pins,
            'pin_net': pin_net,
            'net_pins': {k: v for k, v in net_pins.items()},
            'type_net': dict(type_net)
        }

        # 儲存 session 資訊（後續 /download 會在副本上操作）
        session_data = {"aedb_path": aedb_folder_path, "original_filename": zip_name}
        with open(os.path.join(temp_dir, 'session.json'), 'w', encoding='utf-8') as f:
            json.dump(session_data, f, ensure_ascii=False)

        # 儲存 EDB info 供後續 API 調用
        with open(os.path.join(temp_dir, 'info.json'), 'w', encoding='utf-8') as f:
            json.dump(info, f, ensure_ascii=False)

        return jsonify({'info': info, 'temp_dir': os.path.basename(temp_dir)})

    except Exception as e:
        tb = traceback.format_exc()
        app.logger.error("UPLOAD failed: %s\n%s", e, tb)
        shutil.rmtree(temp_dir, ignore_errors=True)
        return jsonify({'error': str(e), 'traceback': tb}), 500

@app.route('/download', methods=['POST'])
def download_aedb():
    app.logger.debug("DOWNLOAD headers=%s", dict(request.headers))
    try:
        data = request.get_json(silent=False)  # Content-Type 錯會直接丟錯
    except Exception as e:
        app.logger.exception("JSON parse error")
        return jsonify({'error': f'Invalid JSON: {e}'}), 400

    app.logger.debug("DOWNLOAD payload=%s", data)
    ports_config = (data or {}).get('ports')
    temp_dir_name = (data or {}).get('temp_dir')

    if not ports_config or not temp_dir_name:
        app.logger.error("Missing ports or temp_dir. ports=%s, temp_dir=%s", ports_config, temp_dir_name)
        return jsonify({'error': 'Missing ports configuration or temporary directory'}), 400
    
    temp_dir = os.path.join(app.config['UPLOAD_FOLDER'], temp_dir_name)

    session_file = os.path.join(temp_dir, 'session.json')
    if not os.path.exists(session_file):
        app.logger.error("Session file not found: %s", session_file)
        return jsonify({'error': 'Session not found'}), 400

    with open(session_file, 'r', encoding='utf-8') as f:
        session_data = json.load(f)

    src_aedb_path = session_data.get('aedb_path')
    original_filename = session_data.get('original_filename', 'project.zip')

    if not src_aedb_path or not os.path.exists(src_aedb_path):
        app.logger.error("Invalid aedb path: %s", src_aedb_path)
        return jsonify({'error': '.aedb path not found or is invalid'}), 400

    # 為避免「同一路徑二次開啟」，每次都建一個唯一的 aedb 工作副本
    unique_id = uuid.uuid4().hex
    work_aedb_path = os.path.join(temp_dir, f"work_copy_{unique_id}.aedb")
    app.logger.debug("Copying EDB from %s to %s", src_aedb_path, work_aedb_path)
    shutil.copytree(src_aedb_path, work_aedb_path)

    # zip 內的資料夾名稱沿用原始 .aedb 目錄名
    orig_aedb_name = os.path.basename(src_aedb_path)  # e.g. 'Galileo_xxx.aedb'

    try:
        with Edb(work_aedb_path, edbversion=EDB_VERSION) as edb:
            comps = edb.components.components
            nets = edb.nets.nets

            # 建立 (comp, net) 對應的 pin group 與 port terminal（只建一次）
            terminals = {}  # key: (comp, net) -> terminal

            def ensure_terminal(comp_name: str, net_name: str, z0: float):
                key = (comp_name, net_name)
                if key in terminals:
                    return terminals[key]

                if comp_name not in comps:
                    raise ValueError(f"Component '{comp_name}' not found")
                if net_name not in nets:
                    raise ValueError(f"Net '{net_name}' not found")

                # 收集該零件連到指定 net 的 pins
                pin_names = []
                for pin_name, pin in comps[comp_name].pins.items():
                    if get_pin_net_name(pin) == net_name:
                        pin_names.append(pin_name)
                if not pin_names:
                    raise ValueError(f"No pins of component '{comp_name}' connect to net '{net_name}'")

                group_name = f"port_{comp_name}_{net_name}"
                ret = edb.siwave.create_pin_group(comp_name, pin_names, group_name)
                if isinstance(ret, tuple) and len(ret) == 2:
                    _, pin_group = ret
                else:
                    pin_group = ret

                terminal = pin_group.create_port_terminal(float(z0))
                terminals[key] = terminal
                return terminal

            # 解析與建立 terminals
            parsed_ports = []
            for i, p in enumerate(ports_config, 1):
                try:
                    name = str(p["port_name"])
                    pos_comp, pos_net = parse_tuple(p["pos"])
                    neg_comp, neg_net = parse_tuple(p["neg"])
                    z0 = float(p.get("z0", 50))
                except Exception as ex:
                    raise ValueError(f"ports[{i}] invalid entry: {ex}")

                t_sig = ensure_terminal(pos_comp, pos_net, z0)
                t_ref = ensure_terminal(neg_comp, neg_net, z0)
                parsed_ports.append((name, t_sig, t_ref))

            # 設定 reference 關係
            for name, t_sig, t_ref in parsed_ports:
                if hasattr(t_sig, "SetReferenceTerminal"):
                    t_sig.SetReferenceTerminal(t_ref)
                elif hasattr(t_sig, "set_reference_terminal"):
                    t_sig.set_reference_terminal(t_ref)
                else:
                    raise RuntimeError("Port terminal object lacks SetReferenceTerminal method")

            edb.save_edb()

        # ===== 將更新後的 .aedb 內容直接壓入 zip =====
        out_zip = os.path.join(temp_dir, f"{orig_aedb_name}.zip")
        app.logger.debug("Zipping contents of %s into %s", work_aedb_path, out_zip)
        zip_aedb_folder(work_aedb_path, out_zip)

        app.logger.debug("Sending file: %s", out_zip)
        zip_dir = os.path.dirname(out_zip)
        zip_filename = os.path.basename(out_zip)
        return send_from_directory(zip_dir, zip_filename, as_attachment=True, download_name=zip_filename)

    except Exception as e:
        tb = traceback.format_exc()
        app.logger.error("DOWNLOAD failed: %s\n%s", e, tb)
        # 失敗不立刻刪 temp_dir，保留現場便於除錯
        return jsonify({'error': str(e), 'traceback': tb, 'temp_dir': temp_dir}), 500

@app.route('/api/common_components', methods=['POST'])
def get_common_components():
    try:
        data = request.get_json()
        temp_dir_name = data.get('temp_dir')
        nets = data.get('nets', [])

        if not temp_dir_name or not nets:
            return jsonify({'error': 'Missing temp_dir or nets list'}), 400

        temp_dir = os.path.join(app.config['UPLOAD_FOLDER'], temp_dir_name)
        info_file = os.path.join(temp_dir, 'info.json')

        if not os.path.exists(info_file):
            return jsonify({'error': 'Cached info not found'}), 404

        with open(info_file, 'r', encoding='utf-8') as f:
            info = json.load(f)
        
        net_pins = info.get('net_pins', {})
        
        # 取得第一個 net 的元件作為初始集合
        first_net = nets[0]
        if first_net not in net_pins:
            return jsonify({'components': []})
        
        common_components = set(comp for comp, pin in net_pins[first_net])

        # 與後續的 nets 取交集
        for net_name in nets[1:]:
            if not common_components:
                break # 優化：如果已經沒有共同元件，就不用再比了
            if net_name in net_pins:
                current_net_components = set(comp for comp, pin in net_pins[net_name])
                common_components.intersection_update(current_net_components)
            else:
                # 如果有一個 net 不存在，那交集就是空的
                common_components.clear()
                break
        
        return jsonify({'components': sorted(list(common_components))})

    except Exception as e:
        tb = traceback.format_exc()
        app.logger.error("API get_common_components failed: %s\n%s", e, tb)
        return jsonify({'error': str(e), 'traceback': tb}), 500

# -------------------- Entrypoint --------------------
if __name__ == '__main__':
    app.run(host="127.0.0.1", port=5001, debug=True)
