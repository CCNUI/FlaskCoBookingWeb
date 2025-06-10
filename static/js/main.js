document.addEventListener('DOMContentLoaded', function() {

    // --- 预约日历交互 ---
    const bookingModal = document.getElementById('bookingModal');
    if (bookingModal) {
        const scheduleTable = document.querySelector('.schedule-table');
        const closeModalButton = document.querySelector('.close-button');
        const bookingForm = document.getElementById('bookingForm');
        const deleteButton = document.getElementById('deleteButton');
        let activeCell = null;

        // 打开模态框
        const openModal = (cell) => {
            activeCell = cell;
            const date = cell.dataset.date;
            const timeSlot = cell.dataset.timeSlot;
            const currentUser = cell.textContent.trim();

            document.getElementById('modalDate').textContent = date;
            document.getElementById('modalTimeSlot').textContent = timeSlot;
            document.getElementById('modalCurrentUser').textContent = currentUser || '无';
            document.getElementById('nameInput').value = currentUser;
            document.getElementById('modalDateInput').value = date;
            document.getElementById('modalTimeSlotInput').value = timeSlot;

            // 如果没有预约人，禁用删除按钮
            deleteButton.disabled = !currentUser;
            document.getElementById('modalMessage').textContent = '';

            bookingModal.style.display = 'flex';
            document.getElementById('nameInput').focus();
        };

        // 关闭模态框
        const closeModal = () => {
            bookingModal.style.display = 'none';
            activeCell = null;
        };

        // 表格单元格点击事件 (事件委托)
        if (scheduleTable) {
            scheduleTable.addEventListener('click', (event) => {
                if (event.target.tagName === 'TD' && event.target.dataset.date) {
                    openModal(event.target);
                }
            });
        }

        // 关闭按钮
        if (closeModalButton) {
            closeModalButton.addEventListener('click', closeModal);
        }

        // 点击模态框外部关闭
        window.addEventListener('click', (event) => {
            if (event.target === bookingModal) {
                closeModal();
            }
        });

        // 表单提交 (创建/更新)
        if (bookingForm) {
            bookingForm.addEventListener('submit', async (event) => {
                event.preventDefault();
                await submitReservation();
            });
        }

        // 删除按钮
        if (deleteButton) {
            deleteButton.addEventListener('click', async () => {
                // 清空输入框并提交，等同于删除
                document.getElementById('nameInput').value = '';
                await submitReservation();
            });
        }

        // 提交逻辑
        const submitReservation = async () => {
            const formData = new FormData(bookingForm);
            const data = {
                date: formData.get('date'),
                time_slot: formData.get('time_slot'),
                name: formData.get('name').trim()
            };

            try {
                const response = await fetch('/submit_reservation', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(data)
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const result = await response.json();

                const modalMessage = document.getElementById('modalMessage');
                modalMessage.textContent = result.message;
                modalMessage.className = `modal-message ${result.status}`;

                if (result.status === 'success') {
                    activeCell.textContent = result.new_user;
                    setTimeout(closeModal, 1000); // 成功后延迟1秒关闭
                } else if (result.status === 'info') {
                     setTimeout(closeModal, 1000);
                }

            } catch (error) {
                console.error('Error submitting reservation:', error);
                document.getElementById('modalMessage').textContent = '发生网络错误，请稍后重试。';
            }
        };
    }

    // --- 管理员后台交互 ---

    // 折叠面板
    const collapsibles = document.querySelectorAll('.collapsible');
    collapsibles.forEach(button => {
        button.addEventListener('click', function() {
            this.classList.toggle('active');
            const content = this.nextElementSibling;
            const icon = this.querySelector('.toggle-icon');
            if (content.style.display === 'block' || content.style.display === '') {
                content.style.display = 'none';
                icon.textContent = '+';
            } else {
                content.style.display = 'block';
                icon.textContent = '-';
            }
        });
    });

    // 删除特殊日期二次确认
    const deleteForms = document.querySelectorAll('.delete-form');
    deleteForms.forEach(form => {
        form.addEventListener('submit', function(event) {
            if (!confirm('您确定要删除此项吗？此操作不可撤销。')) {
                event.preventDefault();
            }
        });
    });

    // 动态添加/删除时间段
    const timeSlotsContainer = document.getElementById('timeSlotsContainer');
    if (timeSlotsContainer) {
        document.getElementById('addSlotBtn').addEventListener('click', () => {
            const newItem = document.createElement('div');
            newItem.className = 'time-slot-item';
            newItem.innerHTML = `
                <input type="text" name="time_slot" placeholder="HH:MM-HH:MM" required>
                <button type="button" class="button-danger remove-slot-btn">删除</button>
            `;
            timeSlotsContainer.appendChild(newItem);
        });

        timeSlotsContainer.addEventListener('click', (event) => {
            if (event.target.classList.contains('remove-slot-btn')) {
                event.target.parentElement.remove();
            }
        });
    }

});