'use strict';


function browserOK() {
    var winNav = window.navigator;
    var vendorName = winNav.vendor;

    var isChromium = window.chrome;
    var isOpera = typeof window.opr !== "undefined";
    var isFirefox = winNav.userAgent.indexOf("Firefox") > -1;
    var isIEedge = winNav.userAgent.indexOf("Edg") > -1;
    var isIOSChrome = winNav.userAgent.match("CriOS");
    var isGoogleChrome = isChromium !== null
        && typeof isChromium !== "undefined"
        && vendorName === "Google Inc."
        && isOpera === false
        && isIEedge === false;
        //&& (typeof winNav.userAgentData === "undefined" || winNav.userAgentData.brands[0].brand === "Google Chrome");

    if (isIOSChrome) {
        // is Google Chrome on IOS
        return 1;
    } else if (isGoogleChrome) {
        // is Google Chrome
        return 1;
    } else {
        // not Google Chrome 
        return 0;
    }
}