@block TwistToCube begin
    # Frame map of the switched-pivot model (X-MB5): a sensor, not plant physics.
    #
    # The switched pivot hinges about the z axis of the pivot frame K, while the firmware
    # (`TipSequencer`) works in the cube frame C whose x axis is the edge. K is the cyclic
    # permutation of C: x_K = y_C, y_K = z_C, z_K = x_C. The body twist `V = [w; v]` of the
    # impact body (pivot-frame axes) therefore reads in the cube frame as
    #
    #   w_C = (w_z, w_x, w_y),   v_C = (v_z, v_x, v_y)
    @inputs V::Vec{6}
    @outputs Vc::Vec{6}
    @equations begin
        Vc[1] ~ V[3]
        Vc[2] ~ V[1]
        Vc[3] ~ V[2]
        Vc[4] ~ V[6]
        Vc[5] ~ V[4]
        Vc[6] ~ V[5]
    end
end
