@block ModalStress3D begin
    # Modal stress recovery of a FEM flexible body (a component of `ModalBody3D`). The
    # reduction (julia/BGSimFEM) stores the stress of every mode per unit modal coordinate at a
    # few points of the part's surface: the hotspots named in the part spec, then the peak
    # candidates the tool chose so that their largest von Mises tracks the surface peak. With
    # the modal coordinates q (m) the six stress components at point i superpose linearly,
    #
    #   sigma_c[i] = sum_k S_c[i, k] q[k]          (c = xx yy zz xy xz yz, Pa),
    #
    # the rigid motion of the body frame gives no stress, and von Mises is taken of the summed
    # components. The constants come from the reduced-model file (the compiler reads it for the
    # `ModalBody3D` node); a file without stress points gives one zero point.
    #
    # `sigma_vm[1..nh]` is the von Mises stress at the hotspots (without named hotspots, at the
    # first peak candidate) and `sigma_max` the largest von Mises over all the points, an
    # estimate of the peak over the part (the file's `validation.stress.peak_coverage` says how
    # close it comes). Both are smooth functions of q, so they add no switching events: von
    # Mises carries a floor of 1 Pa (sqrt(J2 + 1 Pa^2)) and the maximum is the smooth
    # max(a, b) = (a + b + sqrt((a - b)^2 + 1 Pa^2)) / 2, within ns / 2 Pa of the exact one.
    @constants begin
        nm::Int = 2, [min = 1, max = 48, description = "Number of modal coordinates"]
        ns::Int = 1, [min = 1, max = 64, description = "Number of stress points (hotspots first, then peak candidates)"]
        nh::Int = 1, [min = 1, max = 64, description = "Number of hotspot outputs (the first nh points)"]
        Sxx::Mat{ns,nm} = [0.0 0.0], [unit = "Pa/m", description = "Stress xx per unit modal coordinate at each point"]
        Syy::Mat{ns,nm} = [0.0 0.0], [unit = "Pa/m", description = "Stress yy per unit modal coordinate"]
        Szz::Mat{ns,nm} = [0.0 0.0], [unit = "Pa/m", description = "Stress zz per unit modal coordinate"]
        Sxy::Mat{ns,nm} = [0.0 0.0], [unit = "Pa/m", description = "Stress xy per unit modal coordinate"]
        Sxz::Mat{ns,nm} = [0.0 0.0], [unit = "Pa/m", description = "Stress xz per unit modal coordinate"]
        Syz::Mat{ns,nm} = [0.0 0.0], [unit = "Pa/m", description = "Stress yz per unit modal coordinate"]
    end
    @inputs q::Vec{nm}, [unit = "m"]
    @outputs begin
        sigma_vm::Vec{nh}, [unit = "Pa"]
        sigma_max::Real, [unit = "Pa"]
    end
    @variables begin
        sxx::Vec{ns}, [unit = "Pa", description = "Stress xx at the points"]
        syy::Vec{ns}, [unit = "Pa", description = "Stress yy at the points"]
        szz::Vec{ns}, [unit = "Pa", description = "Stress zz at the points"]
        sxy::Vec{ns}, [unit = "Pa", description = "Stress xy at the points"]
        sxz::Vec{ns}, [unit = "Pa", description = "Stress xz at the points"]
        syz::Vec{ns}, [unit = "Pa", description = "Stress yz at the points"]
        vm::Vec{ns}, [unit = "Pa", description = "von Mises stress at the points"]
        mx::Vec{ns}, [unit = "Pa", description = "Running smooth maximum of vm"]
    end
    @equations begin
        sxx ~ Sxx * q
        syy ~ Syy * q
        szz ~ Szz * q
        sxy ~ Sxy * q
        sxz ~ Sxz * q
        syz ~ Syz * q
        for i in 1:ns
            vm[i] ~ sqrt(0.5 * ((sxx[i] - syy[i]) * (sxx[i] - syy[i]) + (syy[i] - szz[i]) * (syy[i] - szz[i]) +
                                (szz[i] - sxx[i]) * (szz[i] - sxx[i])) +
                         3.0 * (sxy[i] * sxy[i] + sxz[i] * sxz[i] + syz[i] * syz[i]) + 1.0)
        end
        mx[1] ~ vm[1]
        for i in 2:ns
            mx[i] ~ 0.5 * (mx[i - 1] + vm[i] + sqrt((mx[i - 1] - vm[i]) * (mx[i - 1] - vm[i]) + 1.0))
        end
        sigma_max ~ mx[ns]
        for i in 1:nh
            sigma_vm[i] ~ vm[i]
        end
    end
end
