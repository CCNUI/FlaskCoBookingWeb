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

            deleteButton.disabled = !currentUser;
            document.getElementById('modalMessage').textContent = '';

            // 跟踪事件：打开预约弹窗
            _hmt.push(['_trackEvent', 'ReservationModal', 'Action', 'Open']);

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
                    // 跟踪事件：点击日历单元格
                    _hmt.push(['_trackEvent', 'Calendar', 'Click', 'Cell']);
                    openModal(event.target);
                }
            });
        }

        // 关闭按钮
        if (closeModalButton) {
            closeModalButton.addEventListener('click', () => {
                // 跟踪事件：点击关闭按钮
                _hmt.push(['_trackEvent', 'ReservationModal', 'Action', 'Close by Button']);
                closeModal();
            });
        }

        // 点击模态框外部关闭
        window.addEventListener('click', (event) => {
            if (event.target === bookingModal) {
                // 跟踪事件：点击弹窗外部区域关闭
                _hmt.push(['_trackEvent', 'ReservationModal', 'Action', 'Close by Outside Click']);
                closeModal();
            }
        });

        // 表单提交 (创建/更新)
        if (bookingForm) {
            bookingForm.addEventListener('submit', async (event) => {
                event.preventDefault();
                // 跟踪事件：点击“提交”按钮
                _hmt.push(['_trackEvent', 'ReservationModal', 'Click', 'Submit Button']);
                await submitReservation();
            });
        }

        // 删除按钮
        if (deleteButton) {
            deleteButton.addEventListener('click', async () => {
                // 跟踪事件：点击“删除此预约”按钮
                _hmt.push(['_trackEvent', 'ReservationModal', 'Click', 'Delete Button']);
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
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });

                if (!response.ok) { throw new Error(`HTTP error! status: ${response.status}`); }

                const result = await response.json();
                const modalMessage = document.getElementById('modalMessage');
                modalMessage.textContent = result.message;
                modalMessage.className = `modal-message ${result.status}`;

                if (result.status === 'success') {
                    // 根据操作类型，分别跟踪创建、更新、删除的成功事件
                    if (result.action === 'create') {
                        _hmt.push(['_trackEvent', 'ReservationAPI', 'Submit', 'Create Success']);
                    } else if (result.action === 'update') {
                        _hmt.push(['_trackEvent', 'ReservationAPI', 'Submit', 'Update Success']);
                    } else if (result.action === 'delete') {
                        _hmt.push(['_trackEvent', 'ReservationAPI', 'Submit', 'Delete Success']);
                    }
                    activeCell.textContent = result.new_user;
                    setTimeout(closeModal, 1000);
                } else if (result.status === 'info') {
                     setTimeout(closeModal, 1000);
                }

            } catch (error) {
                console.error('Error submitting reservation:', error);
                document.getElementById('modalMessage').textContent = '发生网络错误，请稍后重试。';
                // 跟踪事件：提交时发生网络或服务器错误
                _hmt.push(['_trackEvent', 'ReservationAPI', 'Submit', 'Error']);
            }
        };
    }

    // --- 管理员后台交互 ---

    // 折叠面板
    const collapsibles = document.querySelectorAll('.collapsible');
    collapsibles.forEach(button => {
        button.addEventListener('click', function() { // 改为双击触发
            const content = this.nextElementSibling;
            const panelTitle = this.innerText.split('\n')[0].trim(); // 获取面板标题

            if (content.style.display === 'block') {
                content.style.display = 'none';
                 // 跟踪事件：折叠面板
                _hmt.push(['_trackEvent', 'AdminPanel', 'Toggle', `Collapse - ${panelTitle}`]);
            } else {
                content.style.display = 'block';
                 // 跟踪事件：展开面板
                _hmt.push(['_trackEvent', 'AdminPanel', 'Toggle', `Expand - ${panelTitle}`]);
            }
        });
    });

    // 删除项二次确认
    const deleteForms = document.querySelectorAll('.delete-form');
    deleteForms.forEach(form => {
        form.addEventListener('submit', function(event) {
            const confirmed = confirm('您确定要删除此项吗？此操作不可撤销。');
            if (!confirmed) {
                // 跟踪事件：取消删除
                _hmt.push(['_trackEvent', 'AdminPanel', 'Confirmation', 'Delete Canceled']);
                event.preventDefault();
            } else {
                // 跟踪事件：确认删除
                _hmt.push(['_trackEvent', 'AdminPanel', 'Confirmation', 'Delete Confirmed']);
            }
        });
    });

    // 动态添加/删除时间段
    const timeSlotsContainer = document.getElementById('timeSlotsContainer');
    if (timeSlotsContainer) {
        document.getElementById('addSlotBtn').addEventListener('click', () => {
            // 跟踪事件：后台-添加时间段字段
            _hmt.push(['_trackEvent', 'AdminPanel', 'TimeSlots', 'Add Field']);
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
                // 跟踪事件：后台-删除时间段字段
                _hmt.push(['_trackEvent', 'AdminPanel', 'TimeSlots', 'Remove Field']);
                event.target.parentElement.remove();
            }
        });
    }

});