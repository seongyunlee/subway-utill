const guide = document.getElementById("guide");
const zoomIn = document.getElementById("zoomIn");
const zoomOut = document.getElementById("zoomOut");
const svg = document.getElementsByTagName("svg")[0];
const saveButton = document.getElementById("save");
const map = document.getElementById("map");
dragElement(svg);

saveButton.addEventListener("click", captureGuideToPNG);

zoomOut.addEventListener("click", () => {
  let width = svg.viewBox.baseVal.width;
  let height = svg.viewBox.baseVal.height;
  let min_x = svg.viewBox.baseVal.x;
  let min_y = svg.viewBox.baseVal.y;
  svg.setAttribute(
    "viewBox",
    `${min_x} ${min_y} ${width * 1.1} ${height * 1.1}`
  );
});

zoomIn.addEventListener("click", () => {
  let width = svg.viewBox.baseVal.width;
  let height = svg.viewBox.baseVal.height;
  let min_x = svg.viewBox.baseVal.x;
  let min_y = svg.viewBox.baseVal.y;
  svg.setAttribute(
    "viewBox",
    `${min_x} ${min_y} ${width * 0.9} ${height * 0.9}`
  );
});

document.addEventListener("DOMContentLoaded", () => {
  setSvgSize();
  setGuidePosition();
});
document.addEventListener("resize", () => {
  setGuidePosition();
});
function setSvgSize() {
  let width = map.clientWidth;
  let height = map.clientHeight;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
}

function diffSvgMapSize() {
  console.log("SVG", svg.clientWidth, svg.clientHeight);
  console.log("MAP", map.clientWidth, map.clientHeight);
}

function setGuidePosition() {
  guide.style.left = `${
    map.getClientRects()[0].left + map.clientWidth / 2 - guide.clientWidth / 2
  }px`;
  guide.style.top = `${
    map.getClientRects()[0].top + map.clientHeight / 2 - guide.clientHeight / 2
  }px`;
}

function dragElement(elmnt) {
  var pos1 = 0,
    pos2 = 0,
    pos3 = 0,
    pos4 = 0;
  elmnt.onmousedown = dragMouseDown;

  function dragMouseDown(e) {
    e = e || window.event;
    e.preventDefault();
    // get the mouse cursor position at startup:
    pos3 = e.clientX;
    pos4 = e.clientY;
    document.onmouseup = closeDragElement;
    // call a function whenever the cursor moves:
    document.onmousemove = elementDrag;
  }

  function elementDrag(e) {
    e = e || window.event;
    e.preventDefault();
    // calculate the new cursor position:
    pos1 = pos3 - e.clientX;
    pos2 = pos4 - e.clientY;
    pos3 = e.clientX;
    pos4 = e.clientY;
    // set the element's new position:
    let min_y = svg.viewBox.baseVal.y + pos2;
    let min_x = svg.viewBox.baseVal.x + pos1;
    let width = svg.viewBox.baseVal.width;
    let height = svg.viewBox.baseVal.height;

    svg.setAttribute("viewBox", `${min_x} ${min_y} ${width} ${height}`);
  }

  function closeDragElement() {
    /* stop moving when mouse button is released:*/
    document.onmouseup = null;
    document.onmousemove = null;
  }
}

function captureGuideToPNG() {
  guide.style.visibility = "hidden";
  html2canvas(map).then((canvas) => {
    const img = new Image();
    img.src = canvas.toDataURL("image/png");
    img.onload = () => {
      const cropCanvas = document.createElement("canvas");

      const scaleX = img.width / map.clientWidth;
      const scaleY = img.height / map.clientHeight;

      cropCanvas.width = guide.clientWidth * scaleX;
      cropCanvas.height = guide.clientHeight * scaleY;

      cropCanvas
        .getContext("2d")
        .drawImage(
          img,
          (map.clientWidth / 2 - guide.clientWidth / 2) * scaleX,
          (map.clientHeight / 2 - guide.clientHeight / 2) * scaleY,
          guide.clientWidth * scaleX,
          guide.clientHeight * scaleY,
          0,
          0,
          guide.clientWidth * scaleX,
          guide.clientHeight * scaleY
        );

      const org = document.createElement("a");
      org.href = canvas.toDataURL();
      org.download = "original.png";
      org.click();

      const a = document.createElement("a");
      a.href = cropCanvas.toDataURL();
      a.download = "guide.png";
      a.click();

      guide.style.visibility = "visible";
    };
  });
}
