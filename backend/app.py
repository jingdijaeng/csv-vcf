from flask import Flask, request, send_file, jsonify, make_response, render_template
from flask_cors import CORS
import os
import zipfile
import pandas as pd
from functools import wraps
import jwt
import requests

app = Flask(__name__)
CORS(app)

# ตั้งค่าคอนฟิกสำหรับการใช้งาน prefix /csv-vcf
app.config["APPLICATION_ROOT"] = "/csv-vcf"

# ฟังก์ชันตรวจสอบ JWT Token
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get('token')  # รับ Token จาก Cookie
        if not token:
            return jsonify({"error": "Unauthorized access"}), 401
        try:
            jwt.decode(token, app.secret_key, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated


# ฟังก์ชันเข้าสู่ระบบ (Login)
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    login_url = "https://goodmoodgoodcafe.com/wp-json/jwt-auth/v1/token"
    response = requests.post(login_url, json={'username': username, 'password': password})

    if response.status_code == 200:
        token_data = response.json()
        if 'token' not in token_data:
            return jsonify({"error": "Invalid login credentials"}), 401

        token = token_data['token']
        resp = make_response(jsonify({"message": "Login successful"}))
        resp.set_cookie('token', token, httponly=True, secure=True,)
        return resp
    else:
        return jsonify({"error": "Invalid username or password"}), 401


# ฟังก์ชันตรวจสอบสิทธิ์ (Get Data)
@app.route('/get_data', methods=['GET'])
@token_required
def get_data():
    return jsonify({"message": "Access authorized"})


# เสิร์ฟหน้าแอป (App Page)
@app.route('/app.html')
@token_required
def serve_app():
    return render_template('app.html')


# ฟังก์ชันอ่าน CSV
def read_csv_flexibly(file_path):
    encodings_to_try = ['utf-8', 'utf-16', 'ISO-8859-1', 'latin1']
    for encoding in encodings_to_try:
        try:
            return pd.read_csv(file_path, header=None, encoding=encoding), None
        except Exception as e:
            error_message = f"Error reading with encoding {encoding}: {e}"
    return None, error_message


# ฟังก์ชันแปลง CSV เป็น VCF
def csv_to_vcf_flexible(lines, output_file_path, skipped_log_path):
    valid_count = 0
    skipped_numbers = []

    with open(output_file_path, "w", encoding="utf-8") as vcf_file, \
         open(skipped_log_path, "w", encoding="utf-8") as log_file:
        for index, line in enumerate(lines):
            phone = line.strip().replace('+66', '0').replace('-', '').replace(' ', '')
            if not phone.isdigit() or len(phone) < 9 or len(phone) > 15:
                skipped_numbers.append(line.strip())
                log_file.write(f"Skipped: {line.strip()} (Invalid phone number)\n")
                continue
            valid_count += 1
            contact_name = f"Contact {valid_count}"
            vcf_file.write("BEGIN:VCARD\n")
            vcf_file.write("VERSION:3.0\n")
            vcf_file.write(f"N:;{contact_name};;;\n")
            vcf_file.write(f"FN:{contact_name}\n")
            vcf_file.write(f"TEL:{phone}\n")
            vcf_file.write("END:VCARD\n")

    print(f"Total valid numbers: {valid_count}")
    print(f"Total skipped numbers: {len(skipped_numbers)}")


# ฟังก์ชันแยก VCF
def split_vcf_file(file_path, output_folder, chunk_size=500):
    os.makedirs(output_folder, exist_ok=True)
    with open(file_path, "r", encoding="utf-8") as vcf_file:
        lines = vcf_file.readlines()

    chunks = []
    current_chunk = []
    contact_count = 0

    for line in lines:
        current_chunk.append(line)
        if line.strip() == "END:VCARD":
            contact_count += 1

        if contact_count == chunk_size:
            chunks.append(current_chunk)
            current_chunk = []
            contact_count = 0

    if current_chunk:
        chunks.append(current_chunk)

    for idx, chunk in enumerate(chunks):
        chunk_file_path = os.path.join(output_folder, f"chunk_{idx + 1}.vcf")
        with open(chunk_file_path, "w", encoding="utf-8") as chunk_file:
            chunk_file.writelines(chunk)

    return len(chunks), [len([line for line in chunk if line.strip() == "END:VCARD"]) for chunk in chunks]


# ฟังก์ชันแปลงไฟล์ (Convert)
@app.route('/csv-vcf/convert', methods=['POST'])
def convert():
    mode = request.form.get('mode')
    files = request.files.getlist('files[]')

    if not files or not mode:
        return jsonify({"error": "กรุณาเลือกไฟล์และโหมด"}), 400

    output_folder = 'output'
    os.makedirs(output_folder, exist_ok=True)

    if mode == 'csv_to_vcf':
        combined_vcf_path = os.path.join(output_folder, 'output.vcf')
        skipped_log_path = os.path.join(output_folder, 'skipped_numbers.log')

        combined_lines = []
        for file in files:
            file_path = os.path.join(output_folder, file.filename)
            file.save(file_path)
            csv_data, error = read_csv_flexibly(file_path)
            if csv_data is not None:
                combined_lines.extend(csv_data[0].dropna().astype(str).tolist())
            else:
                print(f"Error processing {file.filename}: {error}")

        csv_to_vcf_flexible(combined_lines, combined_vcf_path, skipped_log_path)
        return send_file(combined_vcf_path, as_attachment=True)

    elif mode == 'vcf_to_vcf_500':
        zip_output_path = os.path.join(output_folder, 'vcf_chunks.zip')
        chunk_output_folder = os.path.join(output_folder, 'vcf_chunks')
        file = files[0]
        file_path = os.path.join(output_folder, file.filename)
        file.save(file_path)
        chunk_count, chunk_sizes = split_vcf_file(file_path, chunk_output_folder, chunk_size=500)
        with zipfile.ZipFile(zip_output_path, "w") as zipf:
            for idx in range(chunk_count):
                chunk_file_path = os.path.join(chunk_output_folder, f"chunk_{idx + 1}.vcf")
                zipf.write(chunk_file_path, os.path.basename(chunk_file_path))
        return send_file(zip_output_path, as_attachment=True)

    return jsonify({"error": "โหมดไม่ถูกต้อง"}), 400


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)