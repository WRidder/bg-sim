@block ComposePose2D begin
    @inputs begin
        gp::Vec{3}
        gl::Vec{3}
    end
    @outputs g::Vec{3}
    @equations begin
        # The planar SE(2) chart g = (theta, x, y): g = gp composed with gl, i.e.
        # theta = theta_p + theta_l and p = p_p + R(theta_p) p_l. The fixed-base link pose
        # is composed from q, never integrated (D-MB6).
        g[1] ~ gp[1] + gl[1]
        g[2] ~ gp[2] + cos(gp[1]) * gl[2] - sin(gp[1]) * gl[3]
        g[3] ~ gp[3] + sin(gp[1]) * gl[2] + cos(gp[1]) * gl[3]
    end
end
