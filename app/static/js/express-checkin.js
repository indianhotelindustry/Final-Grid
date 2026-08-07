// Express Check-in Handler
function expressCheckin(resId) {
    const roomId = prompt('Enter Room ID:');
    if (!roomId) return;
    
    fetch(`/api/checkin/express/${resId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || ''
        },
        body: JSON.stringify({room_id: parseInt(roomId)})
    })
    .then(r => r.json())
    .then(data => {
        if(data.success){
            alert('Express check-in completed!');
            location.reload();
        } else {
            alert('Error: ' + data.error);
        }
    })
    .catch(e => alert('Error: ' + e));
}
