setInterval(function () {
    fetch('/get-seats/')
        .then(response => response.json())
        .then(data => {
            data.forEach(course => {
                let el = document.getElementById(`seats-${course.id}`);
                if (el) {
                    el.innerText = course.available_seats;
                }
            });
        });
}, 2000); // updates every 2 seconds