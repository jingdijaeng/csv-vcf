function getTokenFromCookie() {
    const match = document.cookie.match(new RegExp('(^| )token=([^;]+)'));
    return match ? match[2] : null;
}

function validateAndGetToken() {
    const token = getTokenFromCookie();
    if (!token) {
        alert('กรุณาเข้าสู่ระบบก่อน!');
        redirectToLogin();
        return null;
    }
    return token;
}

function redirectToLogin() {
    window.location.href = '/csv-vcf/index.html';
}

function updateResultMessage(message, color = 'black') {
    const resultDiv = document.getElementById('file-result');
    resultDiv.innerHTML = `<p style="color: ${color};">${message}</p>`;
}

function checkAuthentication() {
    validateAndGetToken();
}

function convertFiles() {
    const inputFiles = document.getElementById('inputFiles').files;
    if (inputFiles.length === 0) {
        alert('กรุณาเลือกไฟล์เพื่อแปลง');
        return;
    }

    const token = validateAndGetToken();
    if (!token) return;

    const mode = document.querySelector('input[name="mode"]:checked').value;
    const formData = new FormData();
    formData.append('mode', mode);

    for (let file of inputFiles) {
        formData.append('files[]', file);
    }

    updateResultMessage('กำลังแปลงไฟล์...');

    fetch('/csv-vcf/convert', {
        method: 'POST',
        body: formData,
    })
        .then(response => {
            if (!response.ok) {
                if (response.status === 404) {
                    throw new Error('ไม่พบเส้นทางที่ร้องขอ (Error 404)');
                }
                throw new Error('เกิดข้อผิดพลาดในการแปลงไฟล์');
            }
            return response.blob();
        })
        .then(blob => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = mode === 'csv_to_vcf' ? 'output.vcf' : 'vcf_chunks.zip';
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            updateResultMessage('ดาวน์โหลดไฟล์สำเร็จ!', 'green');
        })
        .catch(error => {
            console.error('Error:', error);
            if (error.message.includes('404')) {
                updateResultMessage('ไม่พบ API ที่ต้องการใช้งาน (Error 404)', 'red');
            } else {
                updateResultMessage('เกิดข้อผิดพลาดในการแปลงไฟล์!', 'red');
            }
        });
}

window.onload = checkAuthentication;

function logout() {
    document.cookie = "token=; path=/; max-age=0";
    localStorage.clear();
    sessionStorage.clear();
    alert('คุณได้ออกจากระบบเรียบร้อยแล้ว!');
    redirectToLogin();
}
