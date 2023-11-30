window.dashExtensions = Object.assign({}, window.dashExtensions, {
    default: {
        function0: function(feature, context) {
            const {
                min,
                max,
                colorscale,
                style,
                colorProp
            } = context.hideout; // get props from hideout
            const value = feature.properties[colorProp]; // get value the determines the color
            const csc = chroma.scale(colorscale).domain([min, max]);
            style.fillColor = csc(value); // set the fill color according to the class
            return style;
        },
        function1: function(feature, latlng, context) {
            console.log(context);
            const min = context.hideout.min;
            const max = context.hideout.max;
            const colorscale = context.hideout.colorscale;
            const circleOptions = context.hideout.circleOptions;
            const colorProp = context.hideout.colorProp;
            const csc = chroma.scale(colorscale).domain([min, max]); // chroma lib to construct colorscale
            circleOptions.fillColor = csc(feature.properties[colorProp]); // set color based on color prop
            return L.circleMarker(latlng, circleOptions); // render a simple circle marker
        },
        function2: function(feature, layer, context) {
            layer.bindTooltip(`${feature.properties.tooltip}`)
        }
    }
});